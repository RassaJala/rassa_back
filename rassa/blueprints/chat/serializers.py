from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from rassa.models import Conversacion, Mensaje, Usuario


class EmisorSerializer(serializers.Serializer):
    id_usuario = serializers.IntegerField(read_only=True)
    nombre_completo = serializers.SerializerMethodField()

    def get_nombre_completo(self, obj):
        persona = obj.fk_persona
        apellido_m = persona.apellido_materno or ""
        return f"{persona.nombre} {persona.apellido_paterno} {apellido_m}".strip()


class MensajeCreateSerializer(serializers.Serializer):
    fk_conversacion = serializers.IntegerField(required=True)
    contenido = serializers.CharField(required=True, min_length=1)

    def validate_fk_conversacion(self, value):
        try:
            conversacion = Conversacion.objects.get(pk=value, estado=True)
        except Conversacion.DoesNotExist as err:
            raise serializers.ValidationError("Conversación no encontrada.") from err

        usuario = self.context.get("usuario")
        if usuario and not usuario.estado:
            raise serializers.ValidationError("Tu cuenta está desactivada.")
        if not conversacion.integrante_set.filter(fk_usuario=usuario, estado=True).exists():
            raise serializers.ValidationError("No eres miembro de esta conversación.")
        return value

    def create(self, validated_data):
        try:
            usuario = self.context["usuario"]
            return Mensaje.objects.create(
                fk_emisor=usuario,
                fk_conversacion_id=validated_data["fk_conversacion"],
                contenido=validated_data["contenido"],
            )
        except IntegrityError as err:
            raise serializers.ValidationError("Error al crear el mensaje.") from err


ALLOWED_EXTENSIONS = {
    "imagen": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "audio": [".mp3", ".wav", ".ogg", ".m4a"],
    "video": [".mp4", ".webm", ".avi", ".mov"],
}


class MensajeDocumentoCreateSerializer(serializers.Serializer):
    fk_conversacion = serializers.IntegerField(required=True)
    tipo_documento = serializers.ChoiceField(choices=["imagen", "audio", "video"], required=True)
    contenido = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    archivo = serializers.FileField(required=True, max_length=None)

    def validate_archivo(self, value):
        if value.size > 20 * 1024 * 1024:
            raise serializers.ValidationError("El archivo no puede superar los 20MB.")
        ext = Path(value.name).suffix.lower()
        tipo = self.initial_data.get("tipo_documento")
        if tipo and ext not in ALLOWED_EXTENSIONS.get(tipo, []):
            raise serializers.ValidationError(f"Extensión {ext} no permitida para tipo {tipo}.")
        return value

    def validate_fk_conversacion(self, value):
        try:
            conversacion = Conversacion.objects.get(pk=value, estado=True)
        except Conversacion.DoesNotExist as err:
            raise serializers.ValidationError("Conversación no encontrada.") from err
        usuario = self.context.get("usuario")
        if usuario and not usuario.estado:
            raise serializers.ValidationError("Tu cuenta está desactivada.")
        if not conversacion.integrante_set.filter(fk_usuario=usuario, estado=True).exists():
            raise serializers.ValidationError("No eres miembro de esta conversación.")
        return value


class MensajeUpdateSerializer(serializers.Serializer):
    contenido = serializers.CharField(required=True, min_length=1)

    def validate(self, attrs):
        mensaje = self.context.get("mensaje")
        usuario = self.context.get("usuario")

        if mensaje.fk_emisor_id != usuario.id_usuario:
            raise serializers.ValidationError("No puedes editar un mensaje que no te pertenece.")

        antiguedad = timezone.now() - mensaje.creado_en
        if antiguedad > timedelta(minutes=15):
            raise serializers.ValidationError("Solo puedes editar mensajes con menos de 15 minutos de antigüedad.")

        return attrs

    def update(self, instance, validated_data):
        instance.contenido = validated_data["contenido"]
        instance.editado = True
        instance.save(update_fields=["contenido", "editado"])
        return instance


class MensajeSerializer(serializers.ModelSerializer):
    emisor = EmisorSerializer(source="fk_emisor", read_only=True)

    class Meta:
        model = Mensaje
        fields = [
            "id_mensaje",
            "emisor",
            "contenido",
            "leido",
            "editado",
            "creado_en",
        ]


class UsuarioBuscarSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()
    rol = serializers.CharField(source="fk_rol.nombre_rol", read_only=True)

    class Meta:
        model = Usuario
        fields = ["id_usuario", "nombre_completo", "correo", "rol"]

    def get_nombre_completo(self, obj):
        p = obj.fk_persona
        am = p.apellido_materno or ""
        return f"{p.nombre} {p.apellido_paterno} {am}".strip()
