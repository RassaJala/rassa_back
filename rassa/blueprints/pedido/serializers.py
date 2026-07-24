"""Serializadores para el módulo de Pedidos."""

from rest_framework import serializers

from rassa.models import DetallePedido, HistorialEstadoPedido, PedidoCabecera

ESTADOS_TERMINALES = {"entregado", "cancelado"}
ESTADOS_CANCELABLES = {"pendiente", "confirmado", "en_preparacion", "listo_para_retirar"}
PRODUCTOS_PREVIEW_LIMIT = 3
ESTADOS_DESTINO = [
    "confirmado",
    "en_preparacion",
    "listo_para_retirar",
    "entregado",
    "cancelado",
]
ESTADOS_DESTINO_CHOICES = [(e, e.replace("_", " ").title()) for e in ESTADOS_DESTINO]


def _nombre_completo(usuario):
    if usuario and usuario.fk_persona:
        p = usuario.fk_persona
        return f"{p.nombre} {p.apellido_paterno}"
    return None


class PedidoListSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.SerializerMethodField()
    vendedor_nombre = serializers.SerializerMethodField()
    estado_actual = serializers.CharField(source="fk_estado.tipo_estado", read_only=True)
    productos = serializers.SerializerMethodField()
    has_more_productos = serializers.SerializerMethodField()

    class Meta:
        model = PedidoCabecera
        fields = [
            "id_pedido",
            "cliente_nombre",
            "vendedor_nombre",
            "productos",
            "has_more_productos",
            "total",
            "estado_actual",
            "creado_en",
        ]

    def get_cliente_nombre(self, obj):
        return _nombre_completo(obj.fk_cliente)

    def get_vendedor_nombre(self, obj):
        return _nombre_completo(obj.fk_vendedor)

    def get_productos(self, obj):
        detalles = getattr(obj, "detallepedido_set", None)
        if detalles is None:
            return []
        return [d.nombre_producto for d in detalles.all()[:PRODUCTOS_PREVIEW_LIMIT]]

    def get_has_more_productos(self, obj):
        detalles = getattr(obj, "detallepedido_set", None)
        if detalles is None:
            return False
        return detalles.count() > PRODUCTOS_PREVIEW_LIMIT


class DetallePedidoSerializer(serializers.ModelSerializer):
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
        return _nombre_completo(obj.fk_cambiado_por)


class PedidoDetailSerializer(serializers.ModelSerializer):
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

    def get_cliente_nombre(self, obj):
        return _nombre_completo(obj.fk_cliente)

    def get_vendedor_nombre(self, obj):
        return _nombre_completo(obj.fk_vendedor)

    def get_detalles(self, obj):
        detalles = getattr(obj, "detallepedido_set", None)
        if detalles is None:
            detalles = DetallePedido.objects.filter(fk_pedido=obj)
        return DetallePedidoSerializer(detalles.all() if hasattr(detalles, "all") else detalles, many=True).data

    def get_historial(self, obj):
        historial = getattr(obj, "historialestadopedido_set", None)
        if historial is None:
            historial = HistorialEstadoPedido.objects.filter(fk_pedido=obj).select_related(
                "fk_estado_anterior", "fk_estado_nuevo", "fk_cambiado_por__fk_persona"
            )
        return HistorialEstadoSerializer(historial.all() if hasattr(historial, "all") else historial, many=True).data


class PedidoCambiarEstadoSerializer(serializers.Serializer):
    nuevo_estado = serializers.ChoiceField(
        choices=ESTADOS_DESTINO_CHOICES,
        error_messages={"invalid_choice": "El estado seleccionado no es válido."},
    )
