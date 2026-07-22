"""Vistas para el módulo de Pedidos."""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from rassa.models import EstadoPedido, HistorialEstadoPedido, PedidoCabecera
from rassa.permissions.role_permissions import HasRole
from rassa.views import _log, ok_response

from .serializers import (
    ESTADOS_CANCELABLES,
    ESTADOS_TERMINALES,
    PedidoCambiarEstadoSerializer,
    PedidoDetailSerializer,
    PedidoListSerializer,
)

SECUENCIA = {
    "pendiente": "confirmado",
    "confirmado": "en_preparacion",
    "en_preparacion": "listo_para_retirar",
    "listo_para_retirar": "entregado",
}


class PedidoViewSet(viewsets.ModelViewSet):
    """ViewSet para la gestión de Pedidos."""

    serializer_class = PedidoListSerializer
    permission_classes = [IsAuthenticated, HasRole("Vendedor", "Admin")]

    def get_queryset(self):
        qs = PedidoCabecera.objects.select_related("fk_estado", "fk_cliente__fk_persona", "fk_vendedor__fk_persona")
        if self.request.user.usuario.fk_rol.nombre_rol == "Vendedor":
            qs = qs.filter(fk_vendedor=self.request.user.usuario)
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(fk_estado__tipo_estado=estado)
        return qs.order_by("-creado_en")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PedidoDetailSerializer
        return PedidoListSerializer

    @action(detail=True, methods=["patch"], url_path="status")
    def cambiar_estado(self, request, pk=None):
        """Cambia el estado de un pedido siguiendo la secuencia válida."""
        pedido = self.get_object()
        serializer = PedidoCambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nuevo_estado_str = serializer.validated_data["nuevo_estado"]

        estado_actual = pedido.fk_estado.tipo_estado

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

        nuevo_estado = EstadoPedido.objects.get(tipo_estado=nuevo_estado_str)

        with transaction.atomic():
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

        return ok_response(
            data=PedidoDetailSerializer(pedido).data,
            message=f"Estado cambiado a '{nuevo_estado_str}' correctamente.",
        )
