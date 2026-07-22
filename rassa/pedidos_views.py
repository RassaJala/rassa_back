"""Vistas para el dominio de pedidos e historial de estados."""

import logging

from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from rassa.models import HistorialEstadoPedido, PedidoCabecera
from rassa.pedidos_serializers import HistorialEstadoPedidoSerializer
from rassa.views import _ok

logger = logging.getLogger(__name__)


class PedidoHistorialView(APIView):
    """Endpoint de solo lectura que retorna el historial de estados de un pedido.

    GET /api/pedidos/<int:pk>/historial/

    Respuesta::

        {
            "data": [
                {
                    "id_historial": 1,
                    "fk_pedido": 10,
                    "fk_estado_anterior": null,
                    "estado_anterior_nombre": null,
                    "fk_estado_nuevo": 1,
                    "estado_nuevo_nombre": "Pendiente",
                    "fk_cambiado_por": 5,
                    "cambiado_por_nombre": "Juan PÃ©rez",
                    "creado_en": "2026-06-01T09:30:00-03:00"
                },
                ...
            ]
        }
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = "catalog_read"

    def get(self, request, pk):
        if not PedidoCabecera.objects.filter(pk=pk).exists():
            raise NotFound("Pedido no encontrado.")

        historial = (
            HistorialEstadoPedido.objects.filter(fk_pedido_id=pk)
            .select_related("fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona")
            .order_by("creado_en")
        )

        serializer = HistorialEstadoPedidoSerializer(historial, many=True)
        return _ok(data=serializer.data)
