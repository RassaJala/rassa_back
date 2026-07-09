from rest_framework import serializers

from rassa.models import Log


class LogSerializer(serializers.ModelSerializer):
    usuario_correo = serializers.CharField(
        source="fk_usuario.correo", read_only=True, default=None
    )

    class Meta:
        model = Log
        fields = [
            "id_log",
            "fk_usuario",
            "usuario_correo",
            "descripcion",
            "ip",
            "dispositivo",
            "creado_en",
            "estado",
        ]
        read_only_fields = fields
