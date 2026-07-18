"""Serializadores para el módulo de Familias."""

from rest_framework import serializers

from rassa.models import Familia, FamiliaUsuario


class FamiliaSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Familia."""

    jefe_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Familia
        fields = [
            "id_familia",
            "fk_jefe_familia",
            "jefe_nombre",
            "nombre_familia",
            "detalle_familia",
            "creado_en",
            "estado",
        ]
        read_only_fields = ["id_familia", "creado_en", "fk_jefe_familia"]

    def get_jefe_nombre(self, obj) -> str | None:
        """Devuelve el nombre completo del jefe de familia."""
        if obj.fk_jefe_familia and obj.fk_jefe_familia.fk_persona:
            persona = obj.fk_jefe_familia.fk_persona
            return f"{persona.nombre} {persona.apellido_paterno}"
        return None

    def validate_nombre_familia(self, value):
        """Valida que el nombre de la familia no esté vacío o sea muy corto."""
        cleaned_value = value.strip() if value else ""
        if len(cleaned_value) < 3:
            raise serializers.ValidationError("El nombre de la familia debe tener al menos 3 caracteres.")
        return cleaned_value


class FamiliaMiembroSerializer(serializers.ModelSerializer):
    """Serializador para administrar miembros en FamiliaUsuario."""

    usuario_nombre = serializers.SerializerMethodField()
    usuario_correo = serializers.SerializerMethodField()

    class Meta:
        model = FamiliaUsuario
        fields = [
            "id_familia_usuario",
            "fk_usuario",
            "usuario_nombre",
            "usuario_correo",
            "fk_familia",
            "estado",
            "creado_en",
        ]
        read_only_fields = ["id_familia_usuario", "creado_en"]

    def get_usuario_nombre(self, obj) -> str | None:
        """Devuelve el nombre completo del miembro."""
        if obj.fk_usuario and obj.fk_usuario.fk_persona:
            persona = obj.fk_usuario.fk_persona
            return f"{persona.nombre} {persona.apellido_paterno}"
        return None

    def get_usuario_correo(self, obj) -> str | None:
        """Devuelve el correo del miembro."""
        return obj.fk_usuario.correo if obj.fk_usuario else None

    def validate(self, attrs):
        """Valida que el usuario y la familia estén activos y se cumpla la exclusividad de membresías."""
        usuario = attrs.get("fk_usuario", self.instance.fk_usuario if self.instance else None)
        familia = attrs.get("fk_familia", self.instance.fk_familia if self.instance else None)
        estado = attrs.get("estado", self.instance.estado if self.instance else True)

        if estado:
            if usuario and not usuario.estado:
                raise serializers.ValidationError({"fk_usuario": "El usuario especificado está inactivo."})

            if familia and not familia.estado:
                raise serializers.ValidationError(
                    {"fk_familia": "No se pueden agregar miembros a una familia inactiva."}
                )

            if usuario:
                existing = FamiliaUsuario.objects.filter(fk_usuario=usuario, estado=True)
                if self.instance:
                    existing = existing.exclude(pk=self.instance.pk)
                if existing.exists():
                    raise serializers.ValidationError({"fk_usuario": "El usuario ya pertenece a otra familia activa."})

        return attrs
