from rest_framework import serializers

from rassa.models import ProductoImagen


class ProductoImagenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoImagen
        fields = ["id_imagen", "fk_producto", "url", "es_principal", "orden", "creado_en"]
        read_only_fields = ["id_imagen", "creado_en"]

    def validate_url(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("La URL no puede estar vacía.")
        return value.strip()
