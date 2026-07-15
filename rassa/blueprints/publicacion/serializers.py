from rest_framework import serializers

from rassa.models import ProductoSemanal, PublicacionSemanal


class ProductoSemanalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoSemanal
        fields = "__all__"
        read_only_fields = ["id_producto_semanal", "fk_publicacion", "creado_en"]

    def validate_stock(self, value):
        if value <= 0:
            raise serializers.ValidationError("El stock debe ser mayor a 0.")
        return value

    def validate_precio(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0.")
        return value


class ProductoSemanalSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoSemanal
        fields = ["id_producto_semanal", "fk_producto", "fk_unidad", "stock", "precio", "foto", "estado"]
        read_only_fields = ["id_producto_semanal", "fk_publicacion"]


class PublicacionSerializer(serializers.ModelSerializer):
    productos = ProductoSemanalSerializer(many=True, read_only=True, source="productosemanal_set")

    class Meta:
        model = PublicacionSemanal
        fields = ["id_publicacion", "fk_agricultor", "fecha_publicacion", "semana", "estado", "productos", "creado_en"]
        read_only_fields = ["id_publicacion", "fk_agricultor", "fecha_publicacion", "semana", "estado", "creado_en"]
