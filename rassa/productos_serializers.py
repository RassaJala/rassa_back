"""Serializers for product CRUD endpoints."""

from rest_framework import serializers

from rassa.models import CategoriaProducto, Producto, ProductoImagen, Unidad


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = ["id_categoria", "nombre", "descripcion"]


class UnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidad
        fields = ["id_unidad", "tipo"]


class ProductoImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoImagen
        fields = ["id_imagen", "url", "es_principal"]


class ProductoListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings."""

    categoria = CategoriaSerializer(source="fk_categoria", read_only=True)
    unidad = UnidadSerializer(source="fk_unidad", read_only=True)
    imagen_principal = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            "id_producto",
            "nombre_producto",
            "descripcion",
            "precio",
            "stock",
            "es_perecedero",
            "imagen",
            "estado",
            "categoria",
            "unidad",
            "imagen_principal",
            "creado_en",
        ]

    def get_imagen_principal(self, obj):
        img = obj.productoimagen_set.filter(es_principal=True).first()
        return img.url if img else None


class ProductoDetailSerializer(serializers.ModelSerializer):
    """Full serializer for product detail/create/update."""

    categoria = CategoriaSerializer(source="fk_categoria", read_only=True)
    unidad = UnidadSerializer(source="fk_unidad", read_only=True)
    imagenes = ProductoImagenSerializer(
        source="productoimagen_set", many=True, read_only=True
    )
    fk_categoria = serializers.PrimaryKeyRelatedField(
        queryset=CategoriaProducto.objects.all()
    )
    fk_unidad = serializers.PrimaryKeyRelatedField(
        queryset=Unidad.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Producto
        fields = [
            "id_producto",
            "nombre_producto",
            "descripcion",
            "precio",
            "stock",
            "fk_unidad",
            "unidad",
            "es_perecedero",
            "imagen",
            "estado",
            "categoria",
            "fk_categoria",
            "imagenes",
            "creado_en",
        ]

    def validate_nombre_producto(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre del producto es obligatorio.")
        return value.strip()

    def validate_precio(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value
