from rest_framework import serializers

from rassa.models import Conversacion, Mensaje


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
        if not conversacion.integrante_set.filter(fk_usuario=usuario, estado=True).exists():
            raise serializers.ValidationError("No eres miembro de esta conversación.")
        return value

    def create(self, validated_data):
        usuario = self.context["usuario"]
        return Mensaje.objects.create(
            fk_emisor=usuario,
            fk_conversacion_id=validated_data["fk_conversacion"],
            contenido=validated_data["contenido"],
        )


class MensajeSerializer(serializers.ModelSerializer):
    emisor = EmisorSerializer(source="fk_emisor", read_only=True)

    class Meta:
        model = Mensaje
        fields = [
            "id_mensaje",
            "emisor",
            "contenido",
            "leido",
            "creado_en",
        ]
