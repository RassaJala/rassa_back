"""Serializadores para el módulo de Cortes."""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from rassa.models import Corte


class CorteSerializer(serializers.ModelSerializer):
    """Serializer de salida para cortes de caja."""

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
        ]
        read_only_fields = ["id_corte", "monto_teorico", "diferencia", "estado", "creado_en"]


class CorteCreateSerializer(serializers.Serializer):
    """Serializer de entrada para crear un corte."""

    monto_real = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    fecha = serializers.DateField(required=False, default=timezone.localdate)
