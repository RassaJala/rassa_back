from django.core.validators import URLValidator
from rest_framework import serializers

from rassa.models import ProductoImagen


class ProductoImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoImagen
        fields = ["id_imagen", "fk_producto", "url", "es_principal", "orden", "creado_en", "drive_file_id"]
        read_only_fields = ["id_imagen", "creado_en", "drive_file_id"]

    def validate_url(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("La URL no puede estar vacía.")
        value = value.strip()
        url_validator = URLValidator(schemes=["https"])
        try:
            url_validator(value)
        except serializers.ValidationError:
            raise serializers.ValidationError("Solo se permiten URLs HTTPS válidas.") from None
        return value
