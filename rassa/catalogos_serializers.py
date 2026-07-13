"""Serializers for catalog endpoints (municipios, localidades, categorías y unidades)."""

from rest_framework import serializers

from rassa.models import CategoriaProducto, Localidad, Municipio, Unidad


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = ["id_municipio", "nombre"]

    def validate_nombre(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("El nombre no puede estar vacío.")
        if len(value) > 100:
            raise serializers.ValidationError("El nombre no puede tener más de 100 caracteres.")
        return value.strip()


class LocalidadSerializer(serializers.ModelSerializer):
    municipio_id = serializers.IntegerField(source="fk_municipio_id", read_only=True)
    fk_municipio = serializers.PrimaryKeyRelatedField(queryset=Municipio.objects.all(), write_only=True, required=False)

    class Meta:
        model = Localidad
        fields = ["id_localidad", "nombre", "municipio_id", "fk_municipio"]


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = ["id_categoria", "nombre", "descripcion", "estado", "creado_en"]
        read_only_fields = ["id_categoria", "creado_en"]


class UnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidad
        fields = ["id_unidad", "nombre", "abreviatura", "estado", "creado_en"]
        read_only_fields = ["id_unidad", "creado_en"]
        extra_kwargs = {"nombre": {"required": True}, "abreviatura": {"required": True}}

    def _sync_tipo(self, validated_data, instance=None):
        """Keep legacy `tipo` column aligned with `nombre` for backward compatibility."""
        if "nombre" in validated_data and validated_data["nombre"]:
            validated_data["tipo"] = validated_data["nombre"]
        elif instance and instance.nombre:
            validated_data["tipo"] = instance.nombre

    def create(self, validated_data):
        self._sync_tipo(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._sync_tipo(validated_data, instance)
        return super().update(instance, validated_data)
