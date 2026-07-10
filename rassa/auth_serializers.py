"""Auth serializers extracted from apps.accounts.

Uses django.contrib.auth.models.User (not custom AUTH_USER_MODEL)
with username_field explicitly set to "email" since the default
Django User uses "username" as USERNAME_FIELD.

Spanish error messages preserved per spec LOG-5.
"""

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from rassa.models import Localidad, Persona, Rol, Usuario


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Token serializer with Spanish error messages.

    Differentiates between nonexistent email and wrong password
    to return user-friendly Spanish messages (per spec LOG-5).

    username_field is explicitly set to "email" because the default
    Django User model uses "username" as USERNAME_FIELD. This keeps
    the API contract consistent: clients send {"email": ..., "password": ...}.
    """

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()

        if user is None:
            raise serializers.ValidationError(
                "No existe una cuenta con este correo.",
                code="authorization",
            )

        if not user.check_password(password):
            raise serializers.ValidationError(
                "Contraseña incorrecta.",
                code="authorization",
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "No existe una cuenta con este correo.",
                code="authorization",
            )

        refresh = self.get_token(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class UserSerializer(serializers.ModelSerializer):
    """Serializer para ver la información detallada del perfil del usuario."""

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
        ]

    def get_role(self, obj):
        if not obj.fk_rol:
            return None
        rol_name = obj.fk_rol.nombre_rol
        mapping = {
            "Cliente": "buyer",
            "Agricultor": "farmer",
            "Administrador": "admin",
            "Vendedor": "seller",
        }
        return mapping.get(rol_name, rol_name)

    def get_localidad_nombre(self, obj):
        if obj.fk_persona and obj.fk_persona.fk_localidad:
            return obj.fk_persona.fk_localidad.nombre
        return None


class RegisterSerializer(serializers.Serializer):
    """Serializer para el registro completo del usuario."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    telefono = serializers.CharField(max_length=15)
    role = serializers.ChoiceField(choices=[("buyer", "Comprador"), ("farmer", "Agricultor")])
    nombre = serializers.CharField(max_length=100)
    apellido_paterno = serializers.CharField(max_length=100)
    apellido_materno = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fecha_nacimiento = serializers.DateField()
    sexo = serializers.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")])
    domicilio = serializers.CharField(max_length=300)
    fk_localidad = serializers.IntegerField()

    def validate_email(self, value):
        if User.objects.filter(username=value).exists() or User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        if Usuario.objects.filter(correo=value).exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        return value

    def validate_fk_localidad(self, value):
        if not Localidad.objects.filter(id_localidad=value).exists():
            raise serializers.ValidationError("La localidad especificada no existe.")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        role_front = validated_data["role"]

        role_mapping = {
            "buyer": "Cliente",
            "farmer": "Agricultor",
        }
        db_role_name = role_mapping.get(role_front)

        try:
            rol = Rol.objects.get(nombre_rol=db_role_name)
        except Rol.DoesNotExist as err:
            raise serializers.ValidationError({"role": f"El rol {db_role_name} no existe en el sistema."}) from err

        localidad_id = validated_data["fk_localidad"]
        localidad = Localidad.objects.get(id_localidad=localidad_id)

        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)

            persona = Persona.objects.create(
                nombre=validated_data["nombre"],
                apellido_paterno=validated_data["apellido_paterno"],
                apellido_materno=validated_data.get("apellido_materno"),
                fecha_nacimiento=validated_data["fecha_nacimiento"],
                sexo=validated_data["sexo"],
                domicilio=validated_data["domicilio"],
                fk_localidad=localidad,
            )

            usuario = Usuario.objects.create(
                fk_user=user, fk_persona=persona, telefono=validated_data["telefono"], correo=email, fk_rol=rol
            )

        return usuario


class ProfileUpdateSerializer(serializers.Serializer):
    """Serializer para actualizar el perfil del usuario."""

    telefono = serializers.CharField(max_length=15, required=False)
    nombre = serializers.CharField(max_length=100, required=False)
    apellido_paterno = serializers.CharField(max_length=100, required=False)
    apellido_materno = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fecha_nacimiento = serializers.DateField(required=False)
    sexo = serializers.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")], required=False)
    domicilio = serializers.CharField(max_length=300, required=False)
    fk_localidad = serializers.IntegerField(required=False)

    def validate_fk_localidad(self, value):
        if not Localidad.objects.filter(id_localidad=value).exists():
            raise serializers.ValidationError("La localidad especificada no existe.")
        return value

    def update(self, instance, validated_data):
        persona = instance.fk_persona

        with transaction.atomic():
            if "telefono" in validated_data:
                instance.telefono = validated_data["telefono"]
                instance.save()

            if "nombre" in validated_data:
                persona.nombre = validated_data["nombre"]
            if "apellido_paterno" in validated_data:
                persona.apellido_paterno = validated_data["apellido_paterno"]
            if "apellido_materno" in validated_data:
                persona.apellido_materno = validated_data["apellido_materno"]
            if "fecha_nacimiento" in validated_data:
                persona.fecha_nacimiento = validated_data["fecha_nacimiento"]
            if "sexo" in validated_data:
                persona.sexo = validated_data["sexo"]
            if "domicilio" in validated_data:
                persona.domicilio = validated_data["domicilio"]
            if "fk_localidad" in validated_data:
                persona.fk_localidad = Localidad.objects.get(id_localidad=validated_data["fk_localidad"])

            persona.save()

        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer para cambiar la contraseña del usuario."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
