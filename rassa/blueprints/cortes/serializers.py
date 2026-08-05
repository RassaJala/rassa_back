"""Serializadores para el módulo de Cortes."""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from rassa.models import Corte


def _nombre_completo(usuario):
    if usuario and usuario.fk_persona:
        p = usuario.fk_persona
        return f"{p.nombre} {p.apellido_paterno}"
    return None


class CorteSerializer(serializers.ModelSerializer):
    """Serializer de salida para cortes de caja."""

    vendedor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Corte
        fields = [
            "id_corte",
            "fecha",
            "monto_teorico",
            "monto_real",
            "diferencia",
            "estado",
            "creado_en",
            "vendedor_nombre",
        ]
        read_only_fields = ["id_corte", "monto_teorico", "diferencia", "estado", "creado_en"]

    def get_vendedor_nombre(self, obj):
        return _nombre_completo(obj.fk_vendedor)


class CorteCreateSerializer(serializers.Serializer):
    """Serializer de entrada para crear un corte."""

    monto_real = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    fecha = serializers.DateField(required=False, default=timezone.localdate)
