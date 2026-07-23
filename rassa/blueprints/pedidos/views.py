"""Vistas del módulo Pedidos — confirmación de pedidos desde el carrito."""

import logging
from decimal import Decimal

from django.db import models, transaction
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from rassa.models import (
    DetallePedido,
    FamiliaUsuario,
    HistorialEstadoPedido,
    LimiteCliente,
    PedidoCabecera,
    ProductoSemanal,
)
from rassa.permissions.role_permissions import CLIENTE, HasRole
from rassa.views import _log, ok_response

from .serializers import PedidoCreateSerializer, PedidoOutputSerializer

logger = logging.getLogger(__name__)

ESTADO_PENDIENTE_ID = 1


class PedidoCreateView(APIView):
    """Endpoint para confirmar un pedido desde el carrito.

    POST /api/pedidos/
    """

    permission_classes = [permissions.IsAuthenticated, HasRole(CLIENTE)]

    def post(self, request):
        serializer = PedidoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items_data = serializer.validated_data["items"]
        usuario = request.user.usuario

        with transaction.atomic():
            # --- 1. Bloquear productos semanales para evitar race conditions ---
            producto_ids = [i["id_producto_semanal"] for i in items_data]
            productos_semanales = {
                ps.id_producto_semanal: ps
                for ps in ProductoSemanal.objects.select_for_update().filter(pk__in=producto_ids)
            }

            # Verificar que todos existan
            for pid in producto_ids:
                if pid not in productos_semanales:
                    raise ValidationError(f"Producto semanal {pid} no encontrado.")

            # --- 2. Re-validar stock (protege contra cambios entre validación y transacción) ---
            for item in items_data:
                ps = productos_semanales[item["id_producto_semanal"]]
                if item["cantidad"] > ps.stock:
                    raise ValidationError(
                        f"Stock insuficiente para '{ps.fk_producto.nombre_producto}'. "
                        f"Disponible: {ps.stock}, solicitado: {item['cantidad']}."
                    )

            # --- 3. Calcular totales ---
            subtotal = Decimal("0.00")
            detalle_items = []
            for item in items_data:
                ps = productos_semanales[item["id_producto_semanal"]]
                importe = ps.precio * item["cantidad"]
                subtotal += importe
                detalle_items.append(
                    {
                        "producto_semanal": ps,
                        "nombre_producto": ps.fk_producto.nombre_producto,
                        "precio_unitario": ps.precio,
                        "cantidad": item["cantidad"],
                        "importe": importe,
                    }
                )

            iva = (subtotal * Decimal("0.16")).quantize(Decimal("0.01"))
            total = subtotal + iva

            # --- 4. Validar límite de crédito ---
            _validar_limite_credito(usuario, total)

            # --- 5. Descontar stock ---
            for item in items_data:
                ps = productos_semanales[item["id_producto_semanal"]]
                ps.stock -= item["cantidad"]
                ps.save(update_fields=["stock"])

            # --- 6. Crear pedido ---
            pedido = PedidoCabecera.objects.create(
                fk_cliente=usuario,
                fk_estado_id=ESTADO_PENDIENTE_ID,
                subtotal=subtotal,
                iva=iva,
                total=total,
            )

            # --- 7. Crear detalles ---
            detalles = []
            for det in detalle_items:
                detalles.append(
                    DetallePedido(
                        fk_pedido=pedido,
                        fk_producto_semanal=det["producto_semanal"],
                        nombre_producto=det["nombre_producto"],
                        precio_unitario=det["precio_unitario"],
                        cantidad=det["cantidad"],
                        importe=det["importe"],
                    )
                )
            DetallePedido.objects.bulk_create(detalles)

            # --- 8. Registrar historial de estado ---
            HistorialEstadoPedido.objects.create(
                fk_pedido=pedido,
                fk_estado_anterior=None,
                fk_estado_nuevo_id=ESTADO_PENDIENTE_ID,
                fk_cambiado_por=usuario,
            )

        _log(
            request.user,
            f"crear_pedido id={pedido.id_pedido} total={total}",
            request,
        )
        logger.info(
            "Pedido %s creado por cliente %s con %d items",
            pedido.id_pedido,
            usuario.id_usuario,
            len(detalles),
        )

        output = PedidoOutputSerializer(pedido)
        return ok_response(
            data=output.data,
            message="Pedido creado correctamente.",
            status_code=status.HTTP_201_CREATED,
        )


def _validar_limite_credito(usuario, total_pedido: Decimal):
    """Valida que el nuevo pedido no exceda el límite de crédito del cliente o su familia.

    Si el usuario no tiene LimiteCliente asignado, no se aplica restricción.
    Si tiene familia activa, suma los pedidos pendientes de todos los miembros.
    """
    try:
        limite = LimiteCliente.objects.get(fk_usuario=usuario)
    except LimiteCliente.DoesNotExist:
        return  # Sin límite asignado → no hay restricción

    # IDs de usuarios a considerar: el cliente + miembros de su familia activa
    usuario_ids = {usuario.id_usuario}
    familias = FamiliaUsuario.objects.filter(fk_usuario=usuario, estado=True).values_list("fk_familia_id", flat=True)

    if familias:
        miembros = FamiliaUsuario.objects.filter(fk_familia_id__in=familias, estado=True).exclude(fk_usuario=usuario)
        usuario_ids.update(miembros.values_list("fk_usuario_id", flat=True))

    # Suma del total de pedidos pendientes (estado=1) de todos los usuarios del grupo
    gasto_actual = PedidoCabecera.objects.filter(
        fk_cliente_id__in=usuario_ids, fk_estado_id=ESTADO_PENDIENTE_ID
    ).aggregate(total_sum=models.Sum("total"))["total_sum"] or Decimal("0.00")

    nuevo_saldo = gasto_actual + total_pedido
    if nuevo_saldo > limite.monto:
        raise ValidationError(
            f"El pedido excede el límite de crédito. "
            f"Límite: ${limite.monto:.2f}, "
            f"Saldo actual en pedidos pendientes: ${gasto_actual:.2f}, "
            f"Total con este pedido: ${nuevo_saldo:.2f}."
        )
