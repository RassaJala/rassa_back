"""Vistas para el módulo de Pedidos."""

import logging

from django.db import DatabaseError, transaction
from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from rassa.models import EstadoPedido, HistorialEstadoPedido, PedidoCabecera
from rassa.permissions.role_permissions import ADMIN, CLIENTE, VENDEDOR, HasRole
from rassa.views import _log, ok_response

from .serializers import (
    ESTADOS_CANCELABLES,
    ESTADOS_TERMINALES,
    PedidoCambiarEstadoSerializer,
    PedidoDetailSerializer,
    PedidoListSerializer,
)

logger = logging.getLogger(__name__)

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
        if self.action == "retrieve":
            return PedidoDetailSerializer
        return PedidoListSerializer

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
