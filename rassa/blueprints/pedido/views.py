"""Vistas para el módulo de Pedidos."""

import logging
from decimal import Decimal

from django.conf import settings
from django.db import DatabaseError, models, transaction
from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from rassa.models import (
    DetallePedido,
    EstadoPedido,
    FamiliaUsuario,
    HistorialEstadoPedido,
    LimiteCliente,
    PedidoCabecera,
    ProductoSemanal,
)
from rassa.permissions.role_permissions import ADMIN, CLIENTE, VENDEDOR, HasRole
from rassa.views import _log, ok_response

from .serializers import (
    ESTADOS_CANCELABLES,
    ESTADOS_TERMINALES,
    HistorialEstadoSerializer,
    PedidoCambiarEstadoSerializer,
    PedidoCreateSerializer,
    PedidoDetailSerializer,
    PedidoListSerializer,
    PedidoOutputSerializer,
    es_pedido_expirado,
)

logger = logging.getLogger(__name__)


def _get_estado_pendiente_id():
    """Lookup dinámico del ID del estado 'pendiente'.

    Sin caché entre requests: Django ya cachea queries dentro de una conexión.
    """
    # ponytail: sin caché entre tests para evitar stale FK en transacciones nuevas
    return EstadoPedido.objects.get(tipo_estado="pendiente").pk


SECUENCIA = {
    "pendiente": "confirmado",
    "confirmado": "en_preparacion",
    "en_preparacion": "listo_para_retirar",
    "listo_para_retirar": "entregado",
}

ROLE_FILTER_MAP = {
    VENDEDOR: "fk_vendedor",
    CLIENTE: "fk_cliente",
}


class PedidoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PedidoListSerializer
    permission_classes = [IsAuthenticated, HasRole(VENDEDOR, ADMIN, CLIENTE)]

    def _get_usuario_rol(self):
        usuario = getattr(self.request.user, "usuario", None)
        if usuario is None:
            return None, None
        rol = getattr(usuario, "fk_rol", None)
        return usuario, rol.nombre_rol if rol else None

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasRole(CLIENTE)]
        return [IsAuthenticated(), HasRole(VENDEDOR, ADMIN, CLIENTE)]

    def get_queryset(self):
        qs = (
            PedidoCabecera.objects.select_related("fk_estado", "fk_cliente__fk_persona", "fk_vendedor__fk_persona")
            .prefetch_related(
                "detallepedido_set",
                Prefetch(
                    "historialestadopedido_set",
                    queryset=HistorialEstadoPedido.objects.select_related(
                        "fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona"
                    ),
                ),
            )
            .order_by("-creado_en")
        )
        usuario, nombre_rol = self._get_usuario_rol()
        filter_field = ROLE_FILTER_MAP.get(nombre_rol)
        if filter_field:
            qs = qs.filter(**{filter_field: usuario})
        elif nombre_rol != ADMIN:
            qs = qs.none()
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(fk_estado__tipo_estado=estado)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return PedidoCreateSerializer
        if self.action == "retrieve":
            return PedidoDetailSerializer
        return PedidoListSerializer

    # ponytail: create() delega la validación de items a _validar_items_bajo_lock
    # para mantener el bloque atómico legible.

    def create(self, request, *args, **kwargs):
        _, nombre_rol = self._get_usuario_rol()
        if nombre_rol != CLIENTE:
            return ok_response(
                message="Solo los clientes pueden crear pedidos.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items_data = serializer.validated_data["items"]
        usuario = request.user.usuario

        try:
            with transaction.atomic():
                productos_semanales = _validar_items_bajo_lock(items_data)

                subtotal, detalle_items = _calcular_detalle(items_data, productos_semanales)

                iva = (subtotal * settings.IVA_RATE).quantize(Decimal("0.01"))
                total = subtotal + iva

                _validar_limite_credito(usuario, total)

                for item in items_data:
                    ps = productos_semanales[item["id_producto_semanal"]]
                    ps.stock -= item["cantidad"]
                    ps.save(update_fields=["stock"])

                estado_pendiente_id = _get_estado_pendiente_id()
                pedido = PedidoCabecera.objects.create(
                    fk_cliente=usuario,
                    fk_estado_id=estado_pendiente_id,
                    subtotal=subtotal,
                    iva=iva,
                    total=total,
                )

                _crear_detalles_bulk(pedido, detalle_items)

                HistorialEstadoPedido.objects.create(
                    fk_pedido=pedido,
                    fk_estado_anterior=None,
                    fk_estado_nuevo_id=estado_pendiente_id,
                    fk_cambiado_por=usuario,
                )

                # Recargar dentro de la transacción para evitar N+1 en el serializer
                pedido = (
                    PedidoCabecera.objects.select_related("fk_estado", "fk_cliente__fk_persona")
                    .prefetch_related(
                        Prefetch(
                            "detallepedido_set",
                            queryset=DetallePedido.objects.select_related("fk_producto_semanal"),
                        ),
                    )
                    .get(pk=pedido.pk)
                )

        except DatabaseError as exc:
            logger.error("Error de base de datos al crear pedido: %s", exc)
            return ok_response(
                message="Error al procesar el pedido. Intente de nuevo.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        _log(request.user, f"crear_pedido id={pedido.id_pedido} total={total}", request)
        logger.info(
            "Pedido %s creado por cliente %s con %d items",
            pedido.id_pedido,
            usuario.id_usuario,
            len(detalle_items),
        )

        output = PedidoOutputSerializer(pedido)
        return ok_response(
            data=output.data,
            message="Pedido creado correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def _get_pedido_con_permiso(self, pk):
        qs = PedidoCabecera.objects.select_for_update(nowait=True).prefetch_related("detallepedido_set")
        usuario, nombre_rol = self._get_usuario_rol()
        filter_field = ROLE_FILTER_MAP.get(nombre_rol)
        if filter_field:
            qs = qs.filter(**{filter_field: usuario})
        elif nombre_rol != ADMIN:
            qs = qs.none()
        return qs.get(pk=pk)

    @action(detail=True, methods=["patch"], url_path="status")
    def cambiar_estado(self, request, pk=None):
        _, nombre_rol = self._get_usuario_rol()
        if nombre_rol == CLIENTE:
            return ok_response(
                message="Los clientes no pueden cambiar el estado del pedido.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        serializer = PedidoCambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nuevo_estado_str = serializer.validated_data["nuevo_estado"]

        with transaction.atomic():
            try:
                pedido = self._get_pedido_con_permiso(pk)
            except PedidoCabecera.DoesNotExist:
                return ok_response(
                    message="Pedido no encontrado.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            except DatabaseError:
                return ok_response(
                    message="El pedido está siendo procesado por otro usuario. Intente de nuevo.",
                    status_code=status.HTTP_409_CONFLICT,
                )

            self.check_object_permissions(request, pedido)
            estado_actual = pedido.fk_estado.tipo_estado

            if es_pedido_expirado(pedido):
                return ok_response(
                    message="El pedido expiró y ya no está disponible.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if estado_actual in ESTADOS_TERMINALES:
                return ok_response(
                    message=f"El pedido ya está en estado terminal '{estado_actual}'.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if nuevo_estado_str == "cancelado":
                if estado_actual not in ESTADOS_CANCELABLES:
                    return ok_response(
                        message=f"No se puede cancelar un pedido en estado '{estado_actual}'.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                esperado = SECUENCIA.get(estado_actual)
                if nuevo_estado_str != esperado:
                    return ok_response(
                        message=f"Desde '{estado_actual}' solo se puede avanzar a '{esperado}'.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

            try:
                nuevo_estado = EstadoPedido.objects.get(tipo_estado=nuevo_estado_str)
            except EstadoPedido.DoesNotExist:
                logger.warning(
                    "EstadoPedido '%s' no encontrado en BD (choices del serializer desactualizados)",
                    nuevo_estado_str,
                )
                return ok_response(
                    message=f"El estado '{nuevo_estado_str}' no está configurado en el sistema.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            estado_anterior = pedido.fk_estado
            pedido.fk_estado = nuevo_estado
            pedido.save(update_fields=["fk_estado"])

            HistorialEstadoPedido.objects.create(
                fk_pedido=pedido,
                fk_estado_anterior=estado_anterior,
                fk_estado_nuevo=nuevo_estado,
                fk_cambiado_por=request.user.usuario,
            )

        _log(
            request.user,
            f"cambiar_estado pedido={pedido.id_pedido} {estado_actual}→{nuevo_estado_str}",
            request,
        )

        pedido = (
            PedidoCabecera.objects.select_related("fk_estado", "fk_cliente__fk_persona", "fk_vendedor__fk_persona")
            .prefetch_related(
                "detallepedido_set",
                Prefetch(
                    "historialestadopedido_set",
                    queryset=HistorialEstadoPedido.objects.select_related(
                        "fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona"
                    ),
                ),
            )
            .get(pk=pedido.pk)
        )

        return ok_response(
            data=PedidoDetailSerializer(pedido).data,
            message=f"Estado cambiado a '{nuevo_estado_str}' correctamente.",
        )

    @action(detail=True, methods=["get"], url_path="historial")
    def historial(self, request, pk=None):
        """Historial de cambios de estado de un pedido.

        GET /api/pedidos/{id}/historial/
        """
        qs = PedidoCabecera.objects.all()
        usuario = getattr(request.user, "usuario", None)
        rol = getattr(usuario, "fk_rol", None) if usuario else None
        if rol and rol.nombre_rol == "Vendedor":
            qs = qs.filter(fk_vendedor=usuario)

        if not qs.filter(pk=pk).exists():
            return ok_response(
                message="Pedido no encontrado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        historial = (
            HistorialEstadoPedido.objects.filter(fk_pedido_id=pk)
            .select_related("fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona")
            .order_by("creado_en")
        )

        return ok_response(data=HistorialEstadoSerializer(historial, many=True).data)


def _validar_items_bajo_lock(items_data):
    """Valida items bajo select_for_update con orden consistente.

    Previene TOCTOU: revalida existencia, stock y estados del producto
    DESPUÉS de adquirir el lock de fila.

    También detecta items duplicados para evitar doble descuento de stock.

    Debe ejecutarse DENTRO de transaction.atomic().
    """
    producto_ids = [i["id_producto_semanal"] for i in items_data]

    # Validar duplicados antes de cualquier otra operación
    if len(producto_ids) != len(set(producto_ids)):
        logger.warning("Items duplicados detectados: %s", producto_ids)
        raise ValidationError("No se permiten productos duplicados en un mismo pedido.")

    # Lock rows in consistent order (ORDER BY pk) to prevent deadlocks
    productos_qs = (
        ProductoSemanal.objects.select_for_update()
        .select_related("fk_producto", "fk_publicacion")
        .filter(pk__in=producto_ids)
        .order_by("pk")
    )
    productos_semanales = {ps.id_producto_semanal: ps for ps in productos_qs}

    for pid in producto_ids:
        if pid not in productos_semanales:
            logger.warning("Producto semanal %s no encontrado durante creación de pedido", pid)
            raise ValidationError(f"Producto semanal {pid} no encontrado.")

    for item in items_data:
        ps = productos_semanales[item["id_producto_semanal"]]
        if item["cantidad"] > ps.stock:
            logger.warning(
                "Stock insuficiente para producto %s: disponible %d, solicitado %d",
                ps.fk_producto.nombre_producto,
                ps.stock,
                item["cantidad"],
            )
            raise ValidationError(
                f"Stock insuficiente para '{ps.fk_producto.nombre_producto}'. "
                f"Disponible: {ps.stock}, solicitado: {item['cantidad']}."
            )

        # ponytail: revalida estados bajo select_for_update en ProductoSemanal.
        # Los estados de Producto y PublicacionSemanal se leen desde FK cacheadas
        # (select_related) pero NO están locked explícitamente. Cambios concurrentes
        # a esas tablas son extremadamente raros.
        if ps.estado != ProductoSemanal.ESTADO_ACTIVO:
            logger.warning("Producto semanal %s ya no está activo durante creación de pedido", ps.id_producto_semanal)
            raise ValidationError(f"El producto '{ps.fk_producto.nombre_producto}' ya no está activo.")
        if ps.fk_publicacion.estado != "publicado":
            logger.warning("Publicación %s ya no está disponible durante creación de pedido", ps.fk_publicacion_id)
            raise ValidationError(
                f"La publicación del producto '{ps.fk_producto.nombre_producto}' ya no está disponible."
            )
        if not ps.fk_producto.estado:
            logger.warning("Producto del catálogo %s inactivo durante creación de pedido", ps.fk_producto_id)
            raise ValidationError(f"El producto del catálogo '{ps.fk_producto.nombre_producto}' ya no está activo.")

    return productos_semanales


def _calcular_detalle(items_data, productos_semanales):
    """Calcula subtotal y prepara datos de detalle.

    Debe ejecutarse DENTRO de transaction.atomic().
    """
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
    return subtotal, detalle_items


def _crear_detalles_bulk(pedido, detalle_items):
    """Crea DetallePedido en bulk para un pedido.

    Debe ejecutarse DENTRO de transaction.atomic().
    """
    detalles = [
        DetallePedido(
            fk_pedido=pedido,
            fk_producto_semanal=det["producto_semanal"],
            nombre_producto=det["nombre_producto"],
            precio_unitario=det["precio_unitario"],
            cantidad=det["cantidad"],
            importe=det["importe"],
        )
        for det in detalle_items
    ]
    DetallePedido.objects.bulk_create(detalles)


def _validar_limite_credito(usuario, total_pedido: Decimal):
    """Valida que el nuevo pedido no exceda el límite de crédito del cliente o su familia.

    Debe ejecutarse DENTRO de transaction.atomic() con select_for_update
    para evitar race conditions entre requests concurrentes.
    """
    try:
        limite = LimiteCliente.objects.select_for_update().get(fk_usuario=usuario)
    except LimiteCliente.DoesNotExist:
        return

    usuario_ids = {usuario.id_usuario}
    # ponytail: FamiliaUsuario bajo select_for_update para evitar race conditions
    # en membresías concurrentes.
    familias = list(
        FamiliaUsuario.objects.select_for_update()
        .filter(fk_usuario=usuario, estado=True)
        .order_by("pk")
        .values_list("fk_familia_id", flat=True)
    )

    if familias:
        miembros = (
            FamiliaUsuario.objects.select_for_update()
            .filter(fk_familia_id__in=familias, estado=True)
            .exclude(fk_usuario=usuario)
            .order_by("pk")
        )
        usuario_ids.update(miembros.values_list("fk_usuario_id", flat=True))

    estado_pendiente_id = _get_estado_pendiente_id()
    gasto_actual = PedidoCabecera.objects.select_for_update().filter(
        fk_cliente_id__in=usuario_ids, fk_estado_id=estado_pendiente_id
    ).order_by("pk").aggregate(total_sum=models.Sum("total"))["total_sum"] or Decimal("0.00")

    nuevo_saldo = gasto_actual + total_pedido
    if nuevo_saldo > limite.monto:
        logger.warning(
            "Crédito excedido para usuario %s: límite=%s gasto_actual=%s nuevo_pedido=%s",
            usuario.id_usuario,
            limite.monto,
            gasto_actual,
            total_pedido,
        )
        raise ValidationError(
            f"El pedido excede el límite de crédito. "
            f"Límite: ${limite.monto:.2f}, "
            f"Saldo actual en pedidos pendientes: ${gasto_actual:.2f}, "
            f"Total con este pedido: ${nuevo_saldo:.2f}."
        )
