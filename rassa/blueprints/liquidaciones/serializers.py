"""Serializers para el módulo de Liquidaciones."""

from datetime import date

from rest_framework import serializers

from rassa.models import Liquidacion, LiquidacionVenta, Pago, TipoPago, Usuario
from rassa.permissions.role_permissions import AGRICULTOR
from rassa.utils import nombre_completo


class VentaEnLiquidacionSerializer(serializers.ModelSerializer):
    """Una venta (pedido) que aporta al cálculo de la liquidación."""

    id_pedido = serializers.IntegerField(source="fk_pedido_id", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    total = serializers.DecimalField(source="monto_aportado", max_digits=10, decimal_places=2, read_only=True)
    creado_en = serializers.DateTimeField(source="fk_pedido.creado_en", read_only=True)
    pago_folio = serializers.SerializerMethodField()

    class Meta:
        model = LiquidacionVenta
        fields = [
            "id_pedido",
            "cliente_nombre",
            "total",
            "creado_en",
            "pago_folio",
        ]

    def get_cliente_nombre(self, obj):
        return nombre_completo(obj.fk_pedido.fk_cliente)

    def get_pago_folio(self, obj):
        # Importante: NO usar `pagos.first()` aquí — Django emite una query
        # nueva por cada `obj` (N+1), incluso con prefetch_related.
        # `next(iter(...))` consume la cache del prefetch sin tocar la BD.
        pagos = getattr(obj.fk_pedido, "pago_set", None)
        if pagos is None:
            return None
        first = next(iter(pagos.all()), None)
        return first.folio if first else None


class PagoLiquidacionSerializer(serializers.ModelSerializer):
    """Pago que cancela la liquidación (cuando existe)."""

    tipo_pago_nombre = serializers.CharField(source="fk_tipo.nombre", read_only=True)
    fecha_pago = serializers.DateTimeField(source="creado_en", read_only=True)

    class Meta:
        model = Pago
        fields = [
            "id_pago",
            "folio",
            "tipo_pago_nombre",
            "monto",
            "referencia",
            "fecha_pago",
        ]


class AgricultorNombreMixin:
    """Mixin compartido: agrega `agricultor_nombre` al serializer que
    opera sobre Liquidacion (revisión 4R R2 SUGGESTION sobre duplicación)."""

    def get_agricultor_nombre(self, obj):
        return nombre_completo(obj.fk_agricultor)


class LiquidacionListSerializer(AgricultorNombreMixin, serializers.ModelSerializer):
    agricultor_id = serializers.IntegerField(source="fk_agricultor_id", read_only=True)
    agricultor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Liquidacion
        fields = [
            "id_liquidacion",
            "agricultor_id",
            "agricultor_nombre",
            "periodo_inicio",
            "periodo_fin",
            "monto_ventas",
            "tasa_comision",
            "comision",
            "monto_liquidar",
            "estado",
            "creado_en",
        ]


class LiquidacionDetalleSerializer(AgricultorNombreMixin, serializers.ModelSerializer):
    agricultor_id = serializers.IntegerField(source="fk_agricultor_id", read_only=True)
    agricultor_nombre = serializers.SerializerMethodField()
    ventas = serializers.SerializerMethodField()
    pago_liquidacion = serializers.SerializerMethodField()

    class Meta:
        model = Liquidacion
        fields = [
            "id_liquidacion",
            "agricultor_id",
            "agricultor_nombre",
            "periodo_inicio",
            "periodo_fin",
            "monto_ventas",
            "tasa_comision",
            "comision",
            "monto_liquidar",
            "estado",
            "creado_en",
            "ventas",
            "pago_liquidacion",
        ]

    def get_ventas(self, obj):
        ventas = self.context.get("ventas_queryset")
        if ventas is None:
            return []
        return VentaEnLiquidacionSerializer(ventas, many=True).data

    def get_pago_liquidacion(self, obj):
        pago = obj.fk_pago_liquidacion
        return PagoLiquidacionSerializer(pago).data if pago else None


class CalcularLiquidacionSerializer(serializers.Serializer):
    """Input para POST /api/liquidaciones/calcular/."""

    agricultor = serializers.IntegerField()
    semana = serializers.IntegerField(min_value=1, max_value=53)
    anio = serializers.IntegerField(min_value=2000, max_value=2100)

    def validate_agricultor(self, value):
        try:
            usuario = Usuario.objects.select_related("fk_rol", "fk_persona").get(pk=value)
        except Usuario.DoesNotExist as err:
            raise serializers.ValidationError("El agricultor no existe.") from err
        if usuario.fk_rol.nombre_rol != AGRICULTOR:
            raise serializers.ValidationError("El usuario indicado no tiene rol Agricultor.")
        if not usuario.estado:
            raise serializers.ValidationError("El agricultor está inactivo.")
        self.context["agricultor_obj"] = usuario
        return value

    def validate(self, attrs):
        semana = attrs.get("semana")
        anio = attrs.get("anio")
        if semana is not None and anio is not None:
            try:
                date.fromisocalendar(anio, semana, 1)
            except ValueError as err:
                raise serializers.ValidationError(
                    {"semana": f"La semana {semana} no existe para el año {anio}."}
                ) from err
        return attrs


class MarcarPagadaSerializer(serializers.Serializer):
    """Input para POST /api/liquidaciones/{id}/marcar-pagada/."""

    tipo_pago = serializers.IntegerField()
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_tipo_pago(self, value):
        if not TipoPago.objects.filter(pk=value).exists():
            raise serializers.ValidationError("El tipo de pago no existe.")
        return value
