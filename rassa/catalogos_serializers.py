"""Serializers for catalog endpoints (municipios, localidades, categorías y unidades)."""

from rest_framework import serializers

from rassa.models import CategoriaProducto, Localidad, Municipio, Unidad


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = ["id_municipio", "nombre"]


class LocalidadSerializer(serializers.ModelSerializer):
    municipio_id = serializers.IntegerField(source="fk_municipio_id", read_only=True)

    class Meta:
        model = Localidad
        fields = ["id_localidad", "nombre", "municipio_id"]


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = ["id_categoria", "nombre", "descripcion", "estado", "creado_en"]


class UnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidad
        fields = ["id_unidad", "nombre", "abreviatura", "estado", "creado_en"]
        extra_kwargs = {"nombre": {"required": True}, "abreviatura": {"required": True}}

    def create(self, validated_data):
        if not validated_data.get("nombre"):
            raise serializers.ValidationError({"nombre": "Este campo es obligatorio."})
        if not validated_data.get("abreviatura"):
            raise serializers.ValidationError({"abreviatura": "Este campo es obligatorio."})

        validated_data["tipo"] = validated_data["nombre"]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "nombre" in validated_data and validated_data["nombre"]:
            validated_data["tipo"] = validated_data["nombre"]
        elif instance.nombre:
            validated_data["tipo"] = instance.nombre
        return super().update(instance, validated_data)
