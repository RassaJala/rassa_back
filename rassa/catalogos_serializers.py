"""Serializers for catalog endpoints (municipios, localidades, categorías y unidades)."""

from rest_framework import serializers

from rassa.models import CategoriaProducto, Localidad, Municipio, Unidad

# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------


def _validate_nombre(self, value):
    """Validate a nombre field using the model's max_length as single source of truth.

    Designed to be assigned as ``validate_nombre`` on any ModelSerializer whose
    model has a ``nombre`` CharField — uses ``self.Meta.model`` to read the
    field's ``max_length`` dynamically.
    """
    if not value or not value.strip():
        raise serializers.ValidationError("El nombre no puede estar vacío.")
    max_length = self.Meta.model._meta.get_field("nombre").max_length
    if len(value) > max_length:
        raise serializers.ValidationError(f"El nombre no puede tener más de {max_length} caracteres.")
    return value.strip()


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = ["id_municipio", "nombre"]
        read_only_fields = ["estado"]

    validate_nombre = _validate_nombre


class LocalidadSerializer(serializers.ModelSerializer):
    municipio_id = serializers.IntegerField(source="fk_municipio_id", read_only=True)

    class Meta:
        model = Localidad
        fields = ["id_localidad", "nombre", "municipio_id"]
        read_only_fields = ["fk_municipio", "estado"]

    validate_nombre = _validate_nombre


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = ["id_categoria", "nombre", "descripcion", "estado", "creado_en"]
        read_only_fields = ["id_categoria", "creado_en"]


class CambiarEstadoSerializer(serializers.Serializer):
    """Serializer for toggling active/inactive state of catalog resources.

    Accepts only a boolean ``estado`` field.
    """

    estado = serializers.BooleanField(required=True)

    def validate_estado(self, value):
        if not isinstance(value, bool):
            raise serializers.ValidationError("El estado debe ser un valor booleano.")
        return value


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
