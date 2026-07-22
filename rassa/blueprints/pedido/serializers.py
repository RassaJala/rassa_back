"""Serializadores para el módulo de Pedidos."""

from rest_framework import serializers

from rassa.models import DetallePedido, HistorialEstadoPedido, PedidoCabecera

ESTADOS_TERMINALES = {"entregado", "cancelado"}
ESTADOS_CANCELABLES = {"pendiente", "confirmado", "en_preparacion", "listo_para_retirar"}


class PedidoListSerializer(serializers.ModelSerializer):
    """Serializador para listado de pedidos."""

    cliente_nombre = serializers.SerializerMethodField()
    vendedor_nombre = serializers.SerializerMethodField()
    estado_actual = serializers.CharField(source="fk_estado.tipo_estado", read_only=True)

    class Meta:
        model = PedidoCabecera
        fields = [
            "id_pedido",
            "cliente_nombre",
            "vendedor_nombre",
            "total",
            "estado_actual",
            "creado_en",
        ]

    def _nombre_completo(self, usuario):
        if usuario and usuario.fk_persona:
            p = usuario.fk_persona
            return f"{p.nombre} {p.apellido_paterno}"
        return None

    def get_cliente_nombre(self, obj):
        return self._nombre_completo(obj.fk_cliente)

    def get_vendedor_nombre(self, obj):
        return self._nombre_completo(obj.fk_vendedor)


class DetallePedidoSerializer(serializers.ModelSerializer):
    """Serializador para detalles de un pedido."""

    class Meta:
        model = DetallePedido
        fields = [
            "id_detalle",
            "nombre_producto",
            "precio_unitario",
            "cantidad",
            "importe",
        ]


class HistorialEstadoSerializer(serializers.ModelSerializer):
    """Serializador para historial de cambios de estado."""

    estado_anterior = serializers.SerializerMethodField()
    estado_nuevo = serializers.CharField(source="fk_estado_nuevo.tipo_estado", read_only=True)
    cambiado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = HistorialEstadoPedido
        fields = [
            "id_historial",
            "estado_anterior",
            "estado_nuevo",
            "cambiado_por_nombre",
            "creado_en",
        ]

    def get_estado_anterior(self, obj):
        return obj.fk_estado_anterior.tipo_estado if obj.fk_estado_anterior else None

    def get_cambiado_por_nombre(self, obj):
        if obj.fk_cambiado_por and obj.fk_cambiado_por.fk_persona:
            p = obj.fk_cambiado_por.fk_persona
            return f"{p.nombre} {p.apellido_paterno}"
        return None


class PedidoDetailSerializer(serializers.ModelSerializer):
    """Serializador detallado de un pedido con productos e historial."""

    cliente_nombre = serializers.SerializerMethodField()
    vendedor_nombre = serializers.SerializerMethodField()
    estado_actual = serializers.CharField(source="fk_estado.tipo_estado", read_only=True)
    detalles = serializers.SerializerMethodField()
    historial = serializers.SerializerMethodField()

    class Meta:
        model = PedidoCabecera
        fields = [
            "id_pedido",
            "cliente_nombre",
            "vendedor_nombre",
            "subtotal",
            "iva",
            "total",
            "estado_actual",
            "fecha_expiracion",
            "creado_en",
            "detalles",
            "historial",
        ]

    def _nombre_completo(self, usuario):
        if usuario and usuario.fk_persona:
            p = usuario.fk_persona
            return f"{p.nombre} {p.apellido_paterno}"
        return None

    def get_cliente_nombre(self, obj):
        return self._nombre_completo(obj.fk_cliente)

    def get_vendedor_nombre(self, obj):
        return self._nombre_completo(obj.fk_vendedor)

    def get_detalles(self, obj):
        detalles = DetallePedido.objects.filter(fk_pedido=obj)
        return DetallePedidoSerializer(detalles, many=True).data

    def get_historial(self, obj):
        historial = HistorialEstadoPedido.objects.filter(fk_pedido=obj).select_related(
            "fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona"
        )
        return HistorialEstadoSerializer(historial, many=True).data


class PedidoCambiarEstadoSerializer(serializers.Serializer):
    """Serializador para cambiar el estado de un pedido."""

    nuevo_estado = serializers.ChoiceField(
        choices=[
            ("confirmado", "Confirmado"),
            ("en_preparacion", "En preparación"),
            ("listo_para_retirar", "Listo para retirar"),
            ("entregado", "Entregado"),
            ("cancelado", "Cancelado"),
        ],
        error_messages={"invalid_choice": "El estado seleccionado no es válido."},
    )
