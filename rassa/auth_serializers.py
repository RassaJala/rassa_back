"""Auth serializers for Rassa.

Uses django.contrib.auth.models.User (not custom AUTH_USER_MODEL)
with username_field explicitly set to "email" since the default
Django User uses "username" as USERNAME_FIELD.

Messages in Spanish per spec LOG-5.
"""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from rassa.models import Localidad, Persona, Rol, Usuario

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

ROLE_MAPPING = {
    "buyer": "Cliente",
    "farmer": "Agricultor",
    "seller": "Vendedor",
    "admin": "Admin",
}

ROLE_REVERSE_MAPPING = {
    "Cliente": "buyer",
    "Agricultor": "farmer",
    "Vendedor": "seller",
    "Admin": "admin",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def validate_fk_localidad(self, value):
    """Validate that a localidad exists. Accepts self for DRF method binding."""
    if not Localidad.objects.filter(id_localidad=value).exists():
        raise serializers.ValidationError("La localidad especificada no existe.")
    return value


def _create_usuario_db(validated_data, email, password, rol):
    """Shared DB creation logic for RegisterSerializer and AdminCreateAgricultorSerializer.

    Creates User + Persona + Usuario in a single transaction.
    """
    localidad_id = validated_data["fk_localidad"]
    try:
        localidad = Localidad.objects.get(id_localidad=localidad_id)
    except Localidad.DoesNotExist as err:
        raise serializers.ValidationError({"fk_localidad": "La localidad especificada no existe."}) from err

    apellido_materno = validated_data.get("apellido_materno")
    if apellido_materno == "":
        apellido_materno = None

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)
            persona = Persona.objects.create(
                nombre=validated_data["nombre"],
                apellido_paterno=validated_data["apellido_paterno"],
                apellido_materno=apellido_materno,
                fecha_nacimiento=validated_data["fecha_nacimiento"],
                sexo=validated_data["sexo"],
                domicilio=validated_data["domicilio"],
                fk_localidad=localidad,
            )
            usuario = Usuario.objects.create(
                fk_user=user,
                fk_persona=persona,
                telefono=validated_data["telefono"],
                correo=email,
                fk_rol=rol,
            )
    except IntegrityError as err:
        err_msg = str(err)
        # Inspect the constraint name to give accurate feedback — not all
        # unique constraints are on the email field.
        if "correo" in err_msg or "email" in err_msg or "username" in err_msg or "auth_user" in err_msg:
            raise serializers.ValidationError({"email": "Este correo ya está registrado."}) from err
        if "telefono" in err_msg:
            raise serializers.ValidationError({"telefono": "Este teléfono ya está registrado."}) from err
        # Unknown constraint — surface a generic error so the caller isn't misled
        raise serializers.ValidationError(
            {"non_field_errors": ["Error de integridad al crear el usuario. Contacte al administrador."]}
        ) from err

    return usuario


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Token serializer with ambiguous error messages (prevents email enumeration).

    Returns the same message regardless of whether the email exists or the
    password is wrong, so an attacker cannot determine valid accounts.
    """

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()

        if user is None or not user.check_password(password) or not user.is_active:
            raise InvalidToken("Correo electrónico o contraseña inválidos.")

        self.user = user  # Expose validated user for the view (avoids TOCTOU re-query)

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
    municipio_id = serializers.IntegerField(
        source="fk_persona.fk_localidad.fk_municipio.id_municipio",
        read_only=True,
    )
    municipio_nombre = serializers.SerializerMethodField()

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
            "municipio_id",
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
        if obj.fk_persona and obj.fk_persona.fk_localidad:
            municipio = obj.fk_persona.fk_localidad.fk_municipio
            if municipio:
                return municipio.nombre
        return None


class RegisterSerializer(serializers.Serializer):
    """Serializer para el registro completo del usuario."""

    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    telefono = serializers.CharField(max_length=20)
    role = serializers.ChoiceField(choices=[("buyer", "Comprador"), ("seller", "Vendedor")])
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

    validate_fk_localidad = validate_fk_localidad

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        role_front = validated_data["role"]
        db_role_name = ROLE_MAPPING[role_front]

        try:
            rol = Rol.objects.get(nombre_rol=db_role_name)
        except Rol.DoesNotExist as err:
            raise serializers.ValidationError({"role": f"El rol {db_role_name} no existe en el sistema."}) from err

        return _create_usuario_db(validated_data, email, password, rol)


class AdminCreateAgricultorSerializer(serializers.Serializer):
    """Serializer para que un Admin cree un usuario Agricultor.

    No incluye campo `role` — siempre crea un Agricultor.
    Solo accesible via el endpoint protegido por HasRole('Admin').
    """

    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    telefono = serializers.CharField(max_length=20)
    nombre = serializers.CharField(max_length=100)
    apellido_paterno = serializers.CharField(max_length=100)
    apellido_materno = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fecha_nacimiento = serializers.DateField()
    sexo = serializers.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")])
    domicilio = serializers.CharField(max_length=300)
    fk_localidad = serializers.IntegerField()

    # Reuses RegisterSerializer validators — keeps validation consistent
    # across public and admin flows. If RegisterSerializer.validate_email
    # changes, this follows automatically since it references the bound method.
    validate_email = RegisterSerializer.validate_email
    validate_password = RegisterSerializer.validate_password
    validate_fk_localidad = validate_fk_localidad

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]

        try:
            rol = Rol.objects.get(nombre_rol="Agricultor")
        except Rol.DoesNotExist as err:
            raise serializers.ValidationError(
                {"non_field_errors": ["El rol Agricultor no existe en el sistema."]}
            ) from err

        return _create_usuario_db(validated_data, email, password, rol)


class ProfileUpdateSerializer(serializers.Serializer):
    """Serializer para actualizar el perfil del usuario."""

    telefono = serializers.CharField(max_length=20, required=False)
    nombre = serializers.CharField(max_length=100, required=False)
    apellido_paterno = serializers.CharField(max_length=100, required=False)
    apellido_materno = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    fecha_nacimiento = serializers.DateField(required=False)
    sexo = serializers.ChoiceField(choices=[("M", "Masculino"), ("F", "Femenino"), ("O", "Otro")], required=False)
    domicilio = serializers.CharField(max_length=300, required=False)
    fk_localidad = serializers.IntegerField(required=False)

    validate_fk_localidad = validate_fk_localidad

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


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer para cambiar la contraseña del usuario.

    El refresh token se invalida en la vista (lista negra) para evitar que
    el token anterior siga funcionando después del cambio de contraseña.
    """

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    refresh_token = serializers.CharField(write_only=True, required=False)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
