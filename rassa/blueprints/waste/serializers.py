from django.core.validators import MinValueValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from rassa.models import DecisionMerma, Merma


class DecisionMermaSerializer(serializers.ModelSerializer):
    decision = serializers.CharField(
        validators=[UniqueValidator(queryset=DecisionMerma.objects.all())]
    )

    class Meta:
        model = DecisionMerma
        fields = ["id_decision", "decision", "creado_en", "estado"]
        read_only_fields = ["id_decision", "creado_en"]


class MermaCreateSerializer(serializers.ModelSerializer):
    fk_producto_semanal = serializers.IntegerField(validators=[MinValueValidator(1)])

    class Meta:
        model = Merma
        fields = ["fk_producto_semanal", "cantidad", "motivo", "comentarios", "fk_decision"]

    def validate_fk_decision(self, value):
        if not value.estado:
            raise serializers.ValidationError("La decisión de merma no está activa.")
        return value

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value


class MermaListSerializer(serializers.ModelSerializer):
    producto_info = serializers.SerializerMethodField()
    decision_info = serializers.SerializerMethodField()

    class Meta:
        model = Merma
        fields = [
            "id_merma",
            "fk_producto_semanal",
            "cantidad",
            "motivo",
            "comentarios",
            "fk_decision",
            "creado_en",
            "estado",
            "producto_info",
            "decision_info",
        ]
        read_only_fields = fields

    def get_producto_info(self, obj):
        if obj.fk_producto_semanal is None:
            return None
        ps = obj.fk_producto_semanal
        if ps.fk_producto is None or ps.fk_publicacion is None:
            return None
        return {
            "id": ps.id_producto_semanal,
            "producto": str(ps.fk_producto),
            "publicacion": ps.fk_publicacion.id_publicacion,
            "stock_restante": ps.stock,
        }

    def get_decision_info(self, obj):
        if obj.fk_decision is None:
            return None
        return {
            "id": obj.fk_decision.id_decision,
            "nombre": obj.fk_decision.decision,
        }
