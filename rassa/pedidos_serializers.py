"""Serializers para el dominio de pedidos e historial de estados."""

from rest_framework import serializers

from rassa.models import HistorialEstadoPedido


class HistorialEstadoPedidoSerializer(serializers.ModelSerializer):
    """Serializer de lectura para el historial de cambios de estado de un pedido.

    Incluye los nombres resueltos de los estados y del usuario que realizÃ³
    el cambio, listos para que el frontend los consuma directamente.
    """

    estado_anterior_nombre = serializers.CharField(
        source="fk_estado_anterior.tipo_estado",
        read_only=True,
        default=None,
    )
    estado_nuevo_nombre = serializers.CharField(
        source="fk_estado_nuevo.tipo_estado",
        read_only=True,
    )
    cambiado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = HistorialEstadoPedido
        fields = [
            "id_historial",
            "fk_pedido",
            "fk_estado_anterior",
            "estado_anterior_nombre",
            "fk_estado_nuevo",
            "estado_nuevo_nombre",
            "fk_cambiado_por",
            "cambiado_por_nombre",
            "creado_en",
        ]

    def get_cambiado_por_nombre(self, obj):
        """Retorna el nombre completo del usuario, o None si es automÃ¡tico."""
        if obj.fk_cambiado_por is None:
            return None
        persona = obj.fk_cambiado_por.fk_persona
        return f"{persona.nombre} {persona.apellido_paterno}".strip()
