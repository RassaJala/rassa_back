"""Serializers for catalog endpoints (municipios, localidades)."""

from rest_framework import serializers

from rassa.models import Localidad, Municipio


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
