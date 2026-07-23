"""Serializadores del módulo Pedidos."""

from decimal import Decimal

from rest_framework import serializers

from rassa.models import DetallePedido, PedidoCabecera, ProductoSemanal


class ItemPedidoSerializer(serializers.Serializer):
    """Serializer para cada item del carrito."""

    id_producto_semanal = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)

    def validate_id_producto_semanal(self, value):
        try:
            producto = ProductoSemanal.objects.select_related(
                "fk_producto", "fk_publicacion"
            ).get(pk=value)
        except ProductoSemanal.DoesNotExist:
            raise serializers.ValidationError(
                "El producto semanal no existe."
            )

        if producto.estado != ProductoSemanal.ESTADO_ACTIVO:
            raise serializers.ValidationError(
                "El producto no está activo."
            )

        if producto.fk_publicacion.estado != "publicado":
            raise serializers.ValidationError(
                "La publicación del producto no está disponible."
            )

        if not producto.fk_producto.estado:
            raise serializers.ValidationError(
                "El producto del catálogo no está activo."
            )

        return value

    def validate(self, data):
        producto = ProductoSemanal.objects.get(pk=data["id_producto_semanal"])
        if data["cantidad"] > producto.stock:
            raise serializers.ValidationError(
                f"Stock insuficiente para '{producto.fk_producto.nombre_producto}'. "
                f"Disponible: {producto.stock}, solicitado: {data['cantidad']}."
            )
        return data


class PedidoCreateSerializer(serializers.Serializer):
    """Serializer de entrada para crear un pedido desde el carrito."""

    items = ItemPedidoSerializer(many=True, allow_empty=False)

    def validate_items(self, value):
        if len(value) == 0:
            raise serializers.ValidationError(
                "Debe incluir al menos un producto."
            )
        return value


class DetallePedidoOutputSerializer(serializers.ModelSerializer):
    """Serializer de salida para detalle del pedido."""

    nombre_producto = serializers.CharField()

    class Meta:
        model = DetallePedido
        fields = [
            "id_detalle",
            "fk_producto_semanal",
            "nombre_producto",
            "precio_unitario",
            "cantidad",
            "importe",
        ]


class PedidoOutputSerializer(serializers.ModelSerializer):
    """Serializer de salida para el pedido creado."""

    detalles = DetallePedidoOutputSerializer(many=True, source="detallepedido_set")

    class Meta:
        model = PedidoCabecera
        fields = [
            "id_pedido",
            "fk_cliente",
            "fk_estado",
            "subtotal",
            "iva",
            "total",
            "detalles",
            "creado_en",
        ]
