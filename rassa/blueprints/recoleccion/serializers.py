"""Serializers del módulo de Recolecciones."""

from rest_framework import serializers

from rassa.models import Recoleccion, Usuario
from rassa.permissions.role_permissions import AGRICULTOR

TRANSICIONES_VALIDAS = {
    "pendiente": ["en_ruta", "cancelado"],
    "en_ruta": ["recolectado", "cancelado"],
    "recolectado": [],
    "cancelado": [],
}


class RecoleccionSerializer(serializers.ModelSerializer):
    """Serializer de Recolección con nombre legible del agricultor."""

    agricultor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Recoleccion
        fields = [
            "id_recoleccion",
            "fk_agricultor",
            "agricultor_nombre",
            "fecha_recoleccion",
            "hora_inicio",
            "hora_fin",
            "estado",
            "comentarios",
            "creado_en",
        ]
        read_only_fields = ["id_recoleccion", "estado", "creado_en"]

    def get_agricultor_nombre(self, obj):
        """Retorna el nombre completo del agricultor o None si no tiene."""
        persona = obj.fk_agricultor.fk_persona if obj.fk_agricultor else None
        if persona is None:
            return None
        return f"{persona.nombre} {persona.apellido_paterno}".strip()

    def validate_fk_agricultor(self, value):
        """Valida que el agricultor exista, esté activo y tenga rol Agricultor."""
        if value is None:
            return value
        usuario = Usuario.objects.filter(pk=value.pk).first()
        if usuario is None or not usuario.estado:
            raise serializers.ValidationError("El agricultor especificado no existe o está inactivo.")
        if not usuario.tiene_rol(AGRICULTOR):
            raise serializers.ValidationError("El agricultor especificado no tiene rol Agricultor.")
        return value

    def validate(self, attrs):
        """Evita dos recolecciones activas del mismo agricultor en la misma fecha."""
        estado = attrs.get("estado", self.instance.estado if self.instance else "pendiente")
        if estado == "cancelado":
            return attrs

        agricultor = attrs.get("fk_agricultor")
        fecha = attrs.get("fecha_recoleccion")
        if self.instance:
            agricultor = agricultor or self.instance.fk_agricultor
            fecha = fecha or self.instance.fecha_recoleccion
        if agricultor is None or fecha is None:
            return attrs

        duplicados = Recoleccion.objects.filter(fk_agricultor=agricultor, fecha_recoleccion=fecha).exclude(
            estado="cancelado"
        )
        if self.instance:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if duplicados.exists():
            raise serializers.ValidationError(
                {"fk_agricultor": "El agricultor ya tiene una recolección programada para esta fecha."}
            )
        return attrs


class RecoleccionCambiarEstadoSerializer(serializers.Serializer):
    """Serializer para validar los cambios de estado de una recolección."""

    estado = serializers.ChoiceField(choices=Recoleccion.ESTADO_CHOICES)

    def validate(self, attrs):
        if self.instance is None:
            raise serializers.ValidationError("Recolección no encontrada.")
        estado_actual = self.instance.estado
        estado_nuevo = attrs.get("estado")
        if estado_nuevo == estado_actual:
            raise serializers.ValidationError("La recolección ya está en ese estado.")
        if estado_nuevo not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            raise serializers.ValidationError(f"No se puede cambiar de '{estado_actual}' a '{estado_nuevo}'.")
        return attrs
