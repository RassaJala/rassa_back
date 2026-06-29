from rest_framework import serializers


class MensajeConversacionSerializer(serializers.Serializer):
    id_mensaje = serializers.IntegerField()
    id_usuario = serializers.IntegerField()
    emisor = serializers.CharField()
    contenido = serializers.CharField(allow_null=True, allow_blank=True)
    leido = serializers.BooleanField()
    creado_en = serializers.DateTimeField()

    id_documento = serializers.IntegerField(allow_null=True)
    nombre_documento = serializers.CharField(allow_null=True)
    url_documento = serializers.CharField(allow_null=True)
    tipo_documento = serializers.CharField(allow_null=True)


class EnviarMensajeSerializer(serializers.Serializer):
    fk_emisor = serializers.IntegerField()
    fk_conversacion = serializers.IntegerField()
    contenido = serializers.CharField(min_length=1)


class EditarMensajeSerializer(serializers.Serializer):
    contenido = serializers.CharField(min_length=1)
