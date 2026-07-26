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

    fk_pedido = serializers.IntegerField()
    fk_tipo = serializers.IntegerField()
    monto = serializers.DecimalField(max_digits=10, decimal_places=2)
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_fk_tipo(self, value):
        if not TipoPago.objects.filter(pk=value).exists():
            raise serializers.ValidationError("El tipo de pago no existe.")
        return value

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        pedido_id = attrs.get("fk_pedido")
        monto = attrs.get("monto")

        try:
            pedido = PedidoCabecera.objects.select_related("fk_estado").get(pk=pedido_id)
        except PedidoCabecera.DoesNotExist as err:
            raise serializers.ValidationError({"fk_pedido": "El pedido no existe."}) from err

        estado_actual = pedido.fk_estado.tipo_estado
        if estado_actual != ESTADO_REQUERIDO:
            raise serializers.ValidationError(
                {
                    "fk_pedido": f"Solo se puede registrar pago cuando el pedido está en '{ESTADO_REQUERIDO}'. "
                    f"Estado actual: '{estado_actual}'."
                }
            )

        if Pago.objects.filter(fk_pedido_id=pedido_id).exists():
            raise serializers.ValidationError({"fk_pedido": "Este pedido ya tiene un pago registrado."})

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


class DetallePedidoReciboSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetallePedido
        fields = [
            "id_detalle",
            "nombre_producto",
            "precio_unitario",
            "cantidad",
            "importe",
        ]


class PagoOutputSerializer(serializers.ModelSerializer):
    """Serializer de salida con datos del pago + recibo."""

    tipo_pago = serializers.CharField(source="fk_tipo.nombre", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    vendedor_nombre = serializers.SerializerMethodField()
    pedido_id = serializers.IntegerField(source="fk_pedido.id_pedido", read_only=True)
    total_pedido = serializers.DecimalField(source="fk_pedido.total", max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(source="fk_pedido.subtotal", max_digits=10, decimal_places=2, read_only=True)
    iva = serializers.DecimalField(source="fk_pedido.iva", max_digits=10, decimal_places=2, read_only=True)
    detalles = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            "id_pago",
            "folio",
            "pedido_id",
            "cliente_nombre",
            "vendedor_nombre",
            "tipo_pago",
            "monto",
            "referencia",
            "subtotal",
            "iva",
            "total_pedido",
            "detalles",
            "creado_en",
        ]

    def get_cliente_nombre(self, obj):
        pedido = obj.fk_pedido
        return _nombre_completo(pedido.fk_cliente) if pedido else None

    def get_vendedor_nombre(self, obj):
        pedido = obj.fk_pedido
        return _nombre_completo(pedido.fk_vendedor) if pedido else None

    def get_detalles(self, obj):
        if not obj.fk_pedido:
            return []
        detalles = DetallePedido.objects.filter(fk_pedido=obj.fk_pedido)
        return DetallePedidoReciboSerializer(detalles, many=True).data


class PagoListSerializer(serializers.ModelSerializer):
    """Serializer para listar pagos."""

    tipo_pago = serializers.CharField(source="fk_tipo.nombre", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    pedido_id = serializers.IntegerField(source="fk_pedido.id_pedido", read_only=True)

    class Meta:
        model = Pago
        fields = [
            "id_pago",
            "folio",
            "pedido_id",
            "cliente_nombre",
            "tipo_pago",
            "monto",
            "creado_en",
        ]

    def get_cliente_nombre(self, obj):
        pedido = obj.fk_pedido
        return _nombre_completo(pedido.fk_cliente) if pedido else None
