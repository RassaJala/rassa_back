from django.core.validators import URLValidator
from rest_framework import serializers

from rassa.models import ProductoSemanal, PublicacionSemanal, Usuario


class ProductoSemanalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoSemanal
        fields = [
            "id_producto_semanal",
            "fk_producto",
            "fk_unidad",
            "stock",
            "precio",
            "foto",
            "estado",
            "creado_en",
        ]
        read_only_fields = [
            "id_producto_semanal",
            "fk_publicacion",
            "creado_en",
            "estado",
        ]

    def validate_stock(self, value):
        if value <= 0:
            raise serializers.ValidationError("El stock debe ser mayor a 0.")
        return value

    def validate_precio(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0.")
        return value

    def validate_foto(self, value):
        if value:
            URLValidator()(value)
        return value


class PublicacionSerializer(serializers.ModelSerializer):
    productos = ProductoSemanalSerializer(many=True, read_only=True, source="productosemanal_set")

    class Meta:
        model = PublicacionSemanal
        fields = ["id_publicacion", "fk_agricultor", "fecha_publicacion", "semana", "estado", "productos", "creado_en"]
        read_only_fields = ["id_publicacion", "fk_agricultor", "fecha_publicacion", "semana", "estado", "creado_en"]


class AgricultorResumeSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="fk_persona.nombre")
    apellido = serializers.CharField(source="fk_persona.apellido_paterno")

    class Meta:
        model = Usuario
        fields = ["id_usuario", "nombre", "apellido"]


class ProductoSemanalPublicSerializer(serializers.ModelSerializer):
    producto = serializers.CharField(source="fk_producto.nombre_producto")
    unidad = serializers.CharField(source="fk_unidad.abreviatura")

    class Meta:
        model = ProductoSemanal
        fields = [
            "id_producto_semanal",
            "producto",
            "unidad",
            "stock",
            "precio",
            "foto",
        ]


class PublicacionCurrentSerializer(serializers.ModelSerializer):
    productos = ProductoSemanalPublicSerializer(many=True, source="productosemanal_set")
    agricultor = AgricultorResumeSerializer(source="fk_agricultor")

    class Meta:
        model = PublicacionSemanal
        fields = [
            "id_publicacion",
            "agricultor",
            "fecha_publicacion",
            "semana",
            "productos",
        ]
