"""Serializadores para el módulo de Pagos."""

from decimal import Decimal

from rest_framework import serializers

from rassa.models import DetallePedido, Pago, PedidoCabecera, TipoPago

ESTADO_REQUERIDO = "listo_para_retirar"


class TipoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoPago
        fields = ["id_tipo_pago", "nombre"]


class PagoCreateSerializer(serializers.Serializer):
    """Serializer de entrada para registrar un pago."""

    pedido = serializers.IntegerField()
    tipo_pago = serializers.IntegerField()
    monto = serializers.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = serializers.CharField(max_length=20, required=False, default="efectivo")
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_tipo_pago(self, value):
        if not TipoPago.objects.filter(pk=value).exists():
            raise serializers.ValidationError("El tipo de pago no existe.")
        return value

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        pedido_id = attrs.get("pedido")
        monto = attrs.get("monto")

        try:
            pedido = PedidoCabecera.objects.select_related("fk_estado").get(pk=pedido_id)
        except PedidoCabecera.DoesNotExist as err:
            raise serializers.ValidationError({"pedido": "El pedido no existe."}) from err

        estado_actual = pedido.fk_estado.tipo_estado
        if estado_actual != ESTADO_REQUERIDO:
            raise serializers.ValidationError(
                {
                    "pedido": f"Solo se puede registrar pago cuando el pedido está en '{ESTADO_REQUERIDO}'. "
                    f"Estado actual: '{estado_actual}'."
                }
            )

        if Pago.objects.filter(fk_pedido_id=pedido_id).exists():
            raise serializers.ValidationError({"pedido": "Este pedido ya tiene un pago registrado."})

        if monto is not None and abs(pedido.total - monto) > Decimal("0.001"):
            raise serializers.ValidationError(
                {"monto": f"El monto del pago (${monto}) no coincide con el total del pedido (${pedido.total})."}
            )

        return attrs


def _nombre_completo(usuario):
    if usuario and usuario.fk_persona:
        p = usuario.fk_persona
        return f"{p.nombre} {p.apellido_paterno}"
    return None


class ProductoReciboSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="nombre_producto", read_only=True)
    precio = serializers.DecimalField(source="precio_unitario", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DetallePedido
        fields = [
            "nombre",
            "precio",
            "cantidad",
        ]


class PagoOutputSerializer(serializers.ModelSerializer):
    """Serializer de salida con datos del pago + recibo (formato frontend)."""

    pedido = serializers.IntegerField(source="fk_pedido.id_pedido", read_only=True)
    tipo_pago = serializers.IntegerField(source="fk_tipo_id", read_only=True)
    tipo_pago_nombre = serializers.CharField(source="fk_tipo.nombre", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    cliente_id = serializers.IntegerField(source="fk_pedido.fk_cliente_id", read_only=True)
    total_pedido = serializers.SerializerMethodField()
    fecha_pago = serializers.DateTimeField(source="creado_en", read_only=True)
    productos = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            "id_pago",
            "folio",
            "pedido",
            "tipo_pago",
            "tipo_pago_nombre",
            "cliente_nombre",
            "cliente_id",
            "metodo_pago",
            "monto",
            "referencia",
            "total_pedido",
            "productos",
            "fecha_pago",
        ]

    def get_total_pedido(self, obj):
        return str(obj.fk_pedido.total) if obj.fk_pedido else None

    def get_cliente_nombre(self, obj):
        pedido = obj.fk_pedido
        return _nombre_completo(pedido.fk_cliente) if pedido else None

    def get_productos(self, obj):
        if not obj.fk_pedido:
            return []
        detalles = obj.fk_pedido.detallepedido_set.all()
        return ProductoReciboSerializer(detalles, many=True).data


class PagoListSerializer(serializers.ModelSerializer):
    """Serializer para listar pagos."""

    pedido = serializers.IntegerField(source="fk_pedido.id_pedido", read_only=True)
    tipo_pago_nombre = serializers.CharField(source="fk_tipo.nombre", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    fecha_pago = serializers.DateTimeField(source="creado_en", read_only=True)

    class Meta:
        model = Pago
        fields = [
            "id_pago",
            "folio",
            "pedido",
            "tipo_pago_nombre",
            "cliente_nombre",
            "metodo_pago",
            "monto",
            "fecha_pago",
        ]

    def get_cliente_nombre(self, obj):
        pedido = obj.fk_pedido
        return _nombre_completo(pedido.fk_cliente) if pedido else None
