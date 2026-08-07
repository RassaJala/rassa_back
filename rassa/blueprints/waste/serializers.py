from django.core.validators import MinValueValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from rassa.models import DecisionMerma, DetallePedido, Merma, PedidoCabecera, ProductoSemanal
from rassa.permissions.role_permissions import CLIENTE


class DecisionMermaSerializer(serializers.ModelSerializer):
    decision = serializers.CharField(validators=[UniqueValidator(queryset=DecisionMerma.objects.all())])

    class Meta:
        model = DecisionMerma
        fields = ["id_decision", "decision", "creado_en", "estado"]
        read_only_fields = ["id_decision", "creado_en"]


class MermaCreateSerializer(serializers.ModelSerializer):
    fk_producto_semanal = serializers.IntegerField(validators=[MinValueValidator(1)])
    fk_pedido = serializers.PrimaryKeyRelatedField(queryset=PedidoCabecera.objects.all())

    class Meta:
        model = Merma
        fields = ["fk_producto_semanal", "fk_pedido", "cantidad", "motivo", "comentarios", "fk_decision"]

    def validate(self, attrs):
        pedido = attrs.get("fk_pedido")
        producto_semanal_id = attrs.get("fk_producto_semanal")
        if pedido is not None and producto_semanal_id is not None:
            ps = ProductoSemanal.objects.filter(
                pk=producto_semanal_id,
                estado=ProductoSemanal.ESTADO_ACTIVO,
            ).first()
            if ps is None:
                raise serializers.ValidationError(
                    {"fk_producto_semanal": "El producto semanal no existe o no está activo."}
                )
            if not DetallePedido.objects.filter(
                fk_pedido=pedido, fk_producto_semanal_id=producto_semanal_id
            ).exists():
                raise serializers.ValidationError({"fk_pedido": "El producto semanal no pertenece a este pedido."})
        return attrs

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
    pedido_info = serializers.SerializerMethodField()

    class Meta:
        model = Merma
        fields = [
            "id_merma",
            "fk_producto_semanal",
            "fk_pedido",
            "cantidad",
            "motivo",
            "comentarios",
            "fk_decision",
            "creado_en",
            "estado",
            "producto_info",
            "decision_info",
            "pedido_info",
        ]
        read_only_fields = fields

    @staticmethod
    def _es_cliente(context) -> bool:
        request = context.get("request")
        if request is None or not request.user.is_authenticated:
            return False
        usuario = getattr(request.user, "usuario", None)
        if usuario is None:
            return False
        rol = getattr(usuario, "fk_rol", None)
        return rol is not None and rol.nombre_rol == CLIENTE

    def get_fields(self):
        fields = super().get_fields()
        if self._es_cliente(self.context):
            fields.pop("comentarios", None)
            fields.pop("pedido_info", None)
        return fields

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

    def get_pedido_info(self, obj):
        pedido = obj.fk_pedido
        if pedido is None:
            return None
        cliente = pedido.fk_cliente
        cliente_nombre = None
        if cliente is not None and cliente.fk_persona is not None:
            persona = cliente.fk_persona
            cliente_nombre = f"{persona.nombre} {persona.apellido_paterno}".strip()
        return {
            "id": pedido.id_pedido,
            "cliente": cliente_nombre,
            "estado": pedido.fk_estado.tipo_estado if pedido.fk_estado_id else None,
            "total": str(pedido.total),
        }
