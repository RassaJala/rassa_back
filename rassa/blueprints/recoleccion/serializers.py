"""Serializers del módulo de Recolecciones."""

from django.utils import timezone
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
        # validators vacío a propósito: DRF 3.15.2 autogenera un UniqueTogetherValidator
        # para UniqueConstraints condicionales (get_unique_together_constraints aplica la
        # condition al queryset). Ese validator rompe el shape del error (non_field_errors
        # en vez de la key fk_agricultor). La unicidad la garantiza el UniqueConstraint
        # parcial + el pre-check del serializer + el lock en create.
        validators = []

    def get_agricultor_nombre(self, obj):
        """Retorna el nombre completo del agricultor o None si no tiene."""
        persona = obj.fk_agricultor.fk_persona if obj.fk_agricultor else None
        if persona is None:
            return None
        return f"{persona.nombre} {persona.apellido_paterno}".strip()

    def validate_fk_agricultor(self, value):
        """Valida que el agricultor exista, esté activo y tenga rol Agricultor."""
        if value is None:
            raise serializers.ValidationError("El agricultor es obligatorio.")
        usuario = Usuario.objects.filter(pk=value.pk).first()
        if usuario is None or not usuario.estado:
            raise serializers.ValidationError("El agricultor especificado no existe o está inactivo.")
        if not usuario.tiene_rol(AGRICULTOR):
            raise serializers.ValidationError("El agricultor especificado no tiene rol Agricultor.")
        return value

    def validate(self, attrs):
        """Valida duplicados, orden de horas, pares de horas y fechas pasadas."""
        # La regla both-or-none SOLO aplica cuando el cliente toca las horas en el
        # request. Un PATCH de campos ajenos (p.ej. solo comentarios) sobre una fila
        # legacy con par incompleto no debe fallar: el valor efectivo es el enviado
        # (incluido null explícito) o el del instance solo si la clave no vino.
        toca_horas = "hora_inicio" in attrs or "hora_fin" in attrs
        if toca_horas:
            hora_inicio = attrs.get("hora_inicio", self.instance.hora_inicio if self.instance else None)
            hora_fin = attrs.get("hora_fin", self.instance.hora_fin if self.instance else None)
            if bool(hora_inicio) != bool(hora_fin):
                raise serializers.ValidationError({"hora_fin": "Deben indicarse ambas horas (inicio y fin) o ninguna."})
            if hora_inicio and hora_fin and hora_fin <= hora_inicio:
                raise serializers.ValidationError({"hora_fin": "hora_fin debe ser posterior a hora_inicio."})

        fecha = attrs.get("fecha_recoleccion")
        if fecha and fecha < timezone.localdate():
            raise serializers.ValidationError({"fecha_recoleccion": "La fecha no puede ser anterior a hoy."})

        agricultor = attrs.get("fk_agricultor")
        fecha = attrs.get("fecha_recoleccion")
        if self.instance:
            agricultor = agricultor or self.instance.fk_agricultor
            fecha = fecha or self.instance.fecha_recoleccion
        if agricultor is None or fecha is None:
            return attrs

        # Capa de pre-chequeo para UX: la garantía final de unicidad es el
        # UniqueConstraint parcial (IntegrityError -> 400 en la vista).
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
        estado_actual = self.instance.estado
        estado_nuevo = attrs.get("estado")
        if estado_nuevo == estado_actual:
            raise serializers.ValidationError("La recolección ya está en ese estado.")
        # Completado tardío directo: un pendiente cuya fecha ya pasó puede marcarse
        # directamente recolectado (la recolección sí ocurrió, aunque nunca pasó por
        # en_ruta). Regla de negocio: pendiente vencido -> recolectado se permite;
        # pendiente vencido -> en_ruta se bloquea (abajo).
        if (
            estado_actual == "pendiente"
            and estado_nuevo == "recolectado"
            and self.instance.fecha_recoleccion < timezone.localdate()
        ):
            return attrs
        if estado_nuevo not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            raise serializers.ValidationError(f"No se puede cambiar de '{estado_actual}' a '{estado_nuevo}'.")
        # Solo se bloquea pasar de pendiente -> en_ruta en una fecha pasada.
        # en_ruta -> recolectado SIEMPRE se permite (completado tardío) y cancelar
        # (pendiente/en_ruta -> cancelado) también, independientemente de la fecha.
        if (
            estado_actual == "pendiente"
            and estado_nuevo == "en_ruta"
            and self.instance.fecha_recoleccion < timezone.localdate()
        ):
            raise serializers.ValidationError(
                {
                    "fecha_recoleccion": (
                        "La fecha de la recolección ya pasó; solo se permite cancelarla o marcarla como recolectada."
                    )
                }
            )
        return attrs
