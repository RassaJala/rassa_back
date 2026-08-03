"""Serializers del módulo de Recolecciones."""

from django.utils import timezone
from rest_framework import serializers

from rassa.auth_serializers import ROLE_REVERSE_MAPPING
from rassa.models import Recoleccion, Usuario
from rassa.permissions.role_permissions import AGRICULTOR

# Mensajes compartidos con las vistas del módulo (views.py los importa de aquí).
# Se definen en serializers para evitar imports circulares: views importa
# serializers, así que serializers NO puede importar de views.
MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO = "El agricultor especificado no existe o está inactivo."
MSG_AGRICULTOR_SIN_ROL = "El agricultor especificado no tiene rol Agricultor."
MSG_AGRICULTOR_DUPLICADO = "El agricultor ya tiene una recolección programada para esta fecha."

# Misma derivación que views.ESTADOS_VALIDOS_STR pero acá: evita que el
# error_messages del ChoiceField de estado dependa de views (import circular).
ESTADOS_VALIDOS_STR = ", ".join(c[0] for c in Recoleccion.ESTADO_CHOICES)

TRANSICIONES_VALIDAS = {
    "pendiente": ["en_ruta", "cancelado"],
    "en_ruta": ["recolectado", "cancelado"],
    "recolectado": [],
    "cancelado": [],
}


class RecoleccionSerializer(serializers.ModelSerializer):
    """Serializer de Recolección con nombre legible del agricultor."""

    agricultor_nombre = serializers.SerializerMethodField()

    # Campo declarado explícitamente con error_messages: el autogenerado por el
    # ModelSerializer devuelve mensajes en inglés ("This field may not be null.",
    # 'Invalid pk "99999" - object does not exist.'). Nota: pk_field con
    # validators NO funciona en DRF 3.15.2 (descubierto en una ronda anterior);
    # error_messages sí. La existencia y el null los resuelve el propio campo;
    # validate_fk_agricultor solo valida las reglas de negocio posteriores.
    fk_agricultor = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.all(),
        error_messages={
            "null": "El agricultor es obligatorio.",
            "does_not_exist": MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO,
            "incorrect_type": "El agricultor debe ser un número entero válido.",
        },
    )

    class Meta:
        model = Recoleccion
        fields = [
            "id_recoleccion",
            "fk_agricultor",
            "agricultor_nombre",
            "fecha_recoleccion",
            "hora_inicio",
            "hora_fin",
            "estado",
            "comentarios",
            "creado_en",
        ]
        read_only_fields = ["id_recoleccion", "estado", "creado_en"]
        # validators vacío a propósito: DRF 3.15.2 autogenera un UniqueTogetherValidator
        # para UniqueConstraints condicionales (get_unique_together_constraints aplica la
        # condition al queryset). Ese validator rompe el shape del error (non_field_errors
        # en vez de la key fk_agricultor). La unicidad la garantiza el UniqueConstraint
        # parcial + el pre-check del serializer + el lock en create.
        validators = []

    def get_agricultor_nombre(self, obj):
        """Retorna el nombre completo del agricultor o None si no tiene."""
        persona = obj.fk_agricultor.fk_persona if obj.fk_agricultor else None
        if persona is None:
            return None
        return f"{persona.nombre} {persona.apellido_paterno}".strip()

    def validate_fk_agricultor(self, value):
        """Valida que el agricultor esté activo y tenga rol Agricultor.

        El "es obligatorio" (null) y el "no existe" (does_not_exist) los resuelve
        el propio campo vía error_messages, ANTES de llegar aquí: las ramas de
        None y de usuario inexistente eran código muerto (el PrimaryKeyRelatedField
        rechaza ambos primero). Acá solo quedan las reglas que dependen de que el
        usuario exista.
        """
        if not value.estado:
            raise serializers.ValidationError(MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO)
        if not value.tiene_rol(AGRICULTOR):
            raise serializers.ValidationError(MSG_AGRICULTOR_SIN_ROL)
        return value

    def validate(self, attrs):
        """Valida duplicados, orden de horas, pares de horas y fechas pasadas."""
        # La regla both-or-none SOLO aplica cuando el cliente toca las horas en el
        # request. Un PATCH de campos ajenos (p.ej. solo comentarios) sobre una fila
        # legacy con par incompleto no debe fallar: el valor efectivo es el enviado
        # (incluido null explícito) o el del instance solo si la clave no vino.
        toca_horas = "hora_inicio" in attrs or "hora_fin" in attrs
        if toca_horas:
            # both-or-none por PRESENCIA de claves (XOR), no por truthiness del
            # valor: {"hora_inicio": null} sin hora_fin es un par tocado -> 400,
            # mientras que {"hora_inicio": null, "hora_fin": null} limpia el par
            # explícitamente (válido). Antes se validaba con bool(), y un null
            # explícito en POST se aceptaba silenciosamente, asimétrico con PATCH.
            if ("hora_inicio" in attrs) != ("hora_fin" in attrs):
                raise serializers.ValidationError({"hora_fin": "Deben indicarse ambas horas (inicio y fin) o ninguna."})
            hora_inicio = attrs.get("hora_inicio", self.instance.hora_inicio if self.instance else None)
            hora_fin = attrs.get("hora_fin", self.instance.hora_fin if self.instance else None)
            # Chequeo de VALORES además del XOR de presencia: con ambas claves
            # presentes pero una null ({"hora_inicio": "08:00:00", "hora_fin": null})
            # el par efectivo queda incompleto y el XOR no lo detecta -> 400.
            # Un par null+null explícito sigue siendo válido (limpia el par).
            if bool(hora_inicio) != bool(hora_fin):
                raise serializers.ValidationError({"hora_fin": "Deben indicarse ambas horas (inicio y fin) o ninguna."})
            if hora_inicio and hora_fin and hora_fin <= hora_inicio:
                raise serializers.ValidationError({"hora_fin": "hora_fin debe ser posterior a hora_inicio."})

        fecha = attrs.get("fecha_recoleccion")
        if fecha and fecha < timezone.localdate():
            raise serializers.ValidationError({"fecha_recoleccion": "La fecha no puede ser anterior a hoy."})

        agricultor = attrs.get("fk_agricultor")
        fecha = attrs.get("fecha_recoleccion")
        if self.instance:
            agricultor = agricultor or self.instance.fk_agricultor
            fecha = fecha or self.instance.fecha_recoleccion
        if agricultor is None or fecha is None:
            return attrs

        # Capa de pre-chequeo para UX: la garantía final de unicidad es el
        # UniqueConstraint parcial (IntegrityError -> 400 en la vista).
        duplicados = Recoleccion.objects.filter(fk_agricultor=agricultor, fecha_recoleccion=fecha).exclude(
            estado="cancelado"
        )
        if self.instance:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if duplicados.exists():
            raise serializers.ValidationError({"fk_agricultor": MSG_AGRICULTOR_DUPLICADO})
        return attrs


class AgricultorSerializer(serializers.ModelSerializer):
    """Serializer de agricultor para el selector de recolecciones (Admin/Vendedor)."""

    id_usuario = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(source="fk_persona.nombre", read_only=True)
    apellido_paterno = serializers.CharField(source="fk_persona.apellido_paterno", read_only=True)
    apellido_materno = serializers.CharField(source="fk_persona.apellido_materno", read_only=True, allow_null=True)
    role = serializers.SerializerMethodField()
    localidad = serializers.IntegerField(source="fk_persona.fk_localidad.id_localidad", read_only=True, allow_null=True)
    localidad_nombre = serializers.SerializerMethodField()
    municipio = serializers.IntegerField(
        source="fk_persona.fk_localidad.fk_municipio.id_municipio", read_only=True, allow_null=True
    )
    municipio_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id_usuario",
            "nombre",
            "apellido_paterno",
            "apellido_materno",
            "role",
            "localidad",
            "localidad_nombre",
            "municipio",
            "municipio_nombre",
        ]

    def get_role(self, obj):
        if not obj.fk_rol:
            return None
        return ROLE_REVERSE_MAPPING.get(obj.fk_rol.nombre_rol, obj.fk_rol.nombre_rol)

    def get_localidad_nombre(self, obj):
        if obj.fk_persona and obj.fk_persona.fk_localidad:
            return obj.fk_persona.fk_localidad.nombre
        return None

    def get_municipio_nombre(self, obj):
        localidad = obj.fk_persona.fk_localidad if obj.fk_persona else None
        if localidad and localidad.fk_municipio:
            return localidad.fk_municipio.nombre
        return None


class RecoleccionCambiarEstadoSerializer(serializers.Serializer):
    """Serializer para validar los cambios de estado de una recolección."""

    estado = serializers.ChoiceField(
        choices=Recoleccion.ESTADO_CHOICES,
        error_messages={"invalid_choice": f"Estado inválido. Valores válidos: {ESTADOS_VALIDOS_STR}."},
    )

    def validate(self, attrs):
        estado_actual = self.instance.estado
        estado_nuevo = attrs.get("estado")
        if estado_nuevo == estado_actual:
            raise serializers.ValidationError({"estado": "La recolección ya está en ese estado."})
        # Completado tardío directo: un pendiente cuya fecha ya pasó puede marcarse
        # directamente recolectado (la recolección sí ocurrió, aunque nunca pasó por
        # en_ruta). Regla de negocio: pendiente vencido -> recolectado se permite;
        # pendiente vencido -> en_ruta se bloquea (abajo).
        if (
            estado_actual == "pendiente"
            and estado_nuevo == "recolectado"
            and self.instance.fecha_recoleccion < timezone.localdate()
        ):
            return attrs
        if estado_nuevo not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            raise serializers.ValidationError(
                {"estado": f"No se puede cambiar de '{estado_actual}' a '{estado_nuevo}'."}
            )
        # Solo se bloquea pasar de pendiente -> en_ruta en una fecha pasada.
        # Cancelar (pendiente/en_ruta -> cancelado) se permite siempre,
        # independientemente de la fecha. En_ruta -> recolectado se permite con
        # cualquier fecha: el recolector puede completar antes del día programado
        # (y también editar la fecha de recolección).
        if (
            estado_actual == "pendiente"
            and estado_nuevo == "en_ruta"
            and self.instance.fecha_recoleccion < timezone.localdate()
        ):
            raise serializers.ValidationError(
                {
                    "fecha_recoleccion": (
                        "La fecha de la recolección ya pasó; solo se permite cancelarla o marcarla como recolectada."
                    )
                }
            )
        return attrs
