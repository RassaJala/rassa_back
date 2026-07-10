"""Serializers for catalog endpoints (municipios, localidades)."""

from rest_framework import serializers

from rassa.models import Localidad, Municipio


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = ["id_municipio", "nombre"]


class LocalidadSerializer(serializers.ModelSerializer):
    municipio_id = serializers.IntegerField(source="fk_municipio_id", read_only=True)

    class Meta:
        model = Localidad
        fields = ["id_localidad", "nombre", "municipio_id"]
