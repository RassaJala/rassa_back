from django.db import transaction
from rest_framework import serializers

from rassa.auth_serializers import ROLE_MAPPING, ROLE_REVERSE_MAPPING
from rassa.models import Localidad, Rol, Usuario


class AdminUserSerializer(serializers.ModelSerializer):
    """Serializer para listado y detalle de usuarios (vista admin)."""

    id_usuario = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(source="correo", read_only=True)
    telefono = serializers.CharField(read_only=True)
    role = serializers.SerializerMethodField()
    nombre = serializers.CharField(source="fk_persona.nombre", read_only=True)
    apellido_paterno = serializers.CharField(source="fk_persona.apellido_paterno", read_only=True)
    apellido_materno = serializers.CharField(source="fk_persona.apellido_materno", read_only=True)
    fecha_nacimiento = serializers.DateField(source="fk_persona.fecha_nacimiento", read_only=True)
    genero = serializers.CharField(source="fk_persona.sexo", read_only=True)
    direccion = serializers.CharField(source="fk_persona.domicilio", read_only=True)
    localidad = serializers.IntegerField(source="fk_persona.fk_localidad.id_localidad", read_only=True)
    localidad_nombre = serializers.SerializerMethodField()
    estado = serializers.BooleanField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id_usuario",
            "email",
            "telefono",
            "role",
            "nombre",
            "apellido_paterno",
            "apellido_materno",
            "fecha_nacimiento",
            "genero",
            "direccion",
            "localidad",
            "localidad_nombre",
            "estado",
            "creado_en",
        ]

    def get_role(self, obj):
        if not obj.fk_rol:
            return None
        return ROLE_REVERSE_MAPPING.get(obj.fk_rol.nombre_rol, obj.fk_rol.nombre_rol)

    def get_localidad_nombre(self, obj):
        if obj.fk_persona and obj.fk_persona.fk_localidad:
            return obj.fk_persona.fk_localidad.nombre
        return None


class AdminUserUpdateSerializer(serializers.Serializer):
    """Serializer para actualizar datos de usuario desde el panel admin.

    Permite editar datos de Persona, telÃ©fono y rol.
    """

    telefono = serializers.CharField(max_length=20, required=False)
    nombre = serializers.CharField(max_length=100, required=False)
    apellido_paterno = serializers.CharField(max_length=100, required=False)
    apellido_materno = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fecha_nacimiento = serializers.DateField(required=False)
    sexo = serializers.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")], required=False)
    domicilio = serializers.CharField(max_length=300, required=False)
    fk_localidad = serializers.IntegerField(required=False)
    role = serializers.ChoiceField(
        choices=[
            ("buyer", "Comprador"),
            ("farmer", "Agricultor"),
            ("admin", "Admin"),
            ("seller", "Vendedor"),
        ],
        required=False,
    )

    def validate_fk_localidad(self, value):
        if not Localidad.objects.filter(id_localidad=value).exists():
            raise serializers.ValidationError("La localidad especificada no existe.")
        return value

    def validate_role(self, value):
        db_role_name = ROLE_MAPPING.get(value)
        if not Rol.objects.filter(nombre_rol=db_role_name).exists():
            raise serializers.ValidationError(f"El rol {db_role_name} no existe en el sistema.")
        return value

    def update(self, instance, validated_data):
        persona = instance.fk_persona

        with transaction.atomic():
            if "telefono" in validated_data:
                instance.telefono = validated_data["telefono"]

            if "role" in validated_data:
                db_role_name = ROLE_MAPPING[validated_data["role"]]
                rol = Rol.objects.get(nombre_rol=db_role_name)
                instance.fk_rol = rol

            instance.save()

            if "nombre" in validated_data:
                persona.nombre = validated_data["nombre"]
            if "apellido_paterno" in validated_data:
                persona.apellido_paterno = validated_data["apellido_paterno"]
            if "apellido_materno" in validated_data:
                value = validated_data["apellido_materno"]
                persona.apellido_materno = None if value == "" else value
            if "fecha_nacimiento" in validated_data:
                persona.fecha_nacimiento = validated_data["fecha_nacimiento"]
            if "sexo" in validated_data:
                persona.sexo = validated_data["sexo"]
            if "domicilio" in validated_data:
                persona.domicilio = validated_data["domicilio"]
            if "fk_localidad" in validated_data:
                persona.fk_localidad_id = validated_data["fk_localidad"]

            persona.save()

        return instance
