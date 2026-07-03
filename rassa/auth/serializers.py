"""Serializadores de autenticación para el frontend.

Serializadores diseñados para ser consumidos por el AuthContext.tsx
del frontend React Native. Retornan el formato exacto que espera
el frontend.

Roles del sistema (mismos nombres en backend y frontend):
    - Administrador
    - Vendedor
    - Agricultor
    - Cliente

Formato de respuesta del login:
    {
        "success": true,
        "message": "...",
        "remember": true,
        "access": "jwt...",
        "refresh": "jwt...",
        "user": {
            "id": 1,
            "email": "...",
            "phone_number": "...",
            "role": "Cliente",
            "first_name": "...",
            "last_name": "..."
        }
    }

Referencia:
    Documento Técnico v3, Fase 13.4 - Módulo M3 (Usuarios y Roles).
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from rassa.models import Persona, Usuario, Rol

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """Serializador para login de usuarios.

    Recibe email y password, valida credenciales contra auth_user,
    y retorna tokens JWT junto con los datos del usuario.

    Attributes:
        email: Correo electrónico del usuario (obligatorio).
        password: Contraseña del usuario (obligatorio).
        remember: Si es true, el refresh token tiene más tiempo de vida.
    """

    email = serializers.EmailField(
        required=True,
        help_text="Correo electrónico registrado en el sistema.",
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        help_text="Contraseña del usuario.",
    )
    remember = serializers.BooleanField(
        default=False,
        help_text="Si es true, extiende la vida del refresh token.",
    )

    def validate(self, attrs):
        """Valida credenciales y retorna tokens + datos de usuario.

        Args:
            attrs: Diccionario con email, password y remember.

        Returns:
            Diccionario con success, message, tokens y datos del usuario.

        Raises:
            serializers.ValidationError: Si las credenciales son inválidas.
        """
        email = attrs.get("email")
        password = attrs.get("password")

        # Buscar usuario en auth_user
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"success": False, "message": "No existe una cuenta con este correo."},
                code="authorization",
            ) from exc

        # Verificar contraseña
        if not user.check_password(password):
            raise serializers.ValidationError(
                {"success": False, "message": "Contraseña incorrecta."},
                code="authorization",
            )

        # Verificar que esté activo
        if not user.is_active:
            raise serializers.ValidationError(
                {"success": False, "message": "La cuenta está desactivada."},
                code="authorization",
            )

        # Obtener datos del usuario de negocio
        try:
            usuario = Usuario.objects.select_related("fk_rol", "fk_persona").get(
                correo=email
            )
        except Usuario.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"success": False, "message": "Usuario no registrado en el sistema."},
                code="authorization",
            ) from exc

        # Generar tokens JWT
        refresh = TokenObtainPairSerializer.get_token(user)

        # Retornar rol directamente (mismo nombre en backend y frontend)
        attrs["user_data"] = {
            "id": usuario.id_usuario,
            "email": user.email,
            "phone_number": usuario.telefono,
            "role": usuario.fk_rol.nombre_rol,
            "first_name": usuario.fk_persona.nombre,
            "last_name": (
                f"{usuario.fk_persona.apellido_paterno} "
                f"{usuario.fk_persona.apellido_materno}"
            ),
        }
        attrs["access"] = str(refresh.access_token)
        attrs["refresh"] = str(refresh)
        attrs["success"] = True
        attrs["message"] = "Inicio de sesión exitoso."

        return attrs


class RegisterSerializer(serializers.Serializer):
    """Serializador para registro de nuevos usuarios.

    Crea simultáneamente Persona, Usuario (negocio) y auth_user (Django).
    Retorna tokens JWT y datos del usuario registrado.

    Attributes:
        email: Correo electrónico (obligatorio, único).
        password: Contraseña (obligatorio).
        first_name: Nombre de la persona (obligatorio).
        last_name: Apellido paterno (obligatorio).
        phone_number: Teléfono de contacto (obligatorio).
        role: Rol del usuario (Cliente, Vendedor, Agricultor). Default: Cliente.
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, min_length=6)
    first_name = serializers.CharField(required=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    phone_number = serializers.CharField(required=True, max_length=15)
    role = serializers.ChoiceField(
        choices=["Cliente", "Vendedor", "Agricultor"],
        default="Cliente",
        help_text="Rol del usuario. Mismos nombres que en el backend.",
    )

    def validate_email(self, value):
        """Valida que el correo no esté registrado.

        Args:
            value: Correo electrónico a validar.

        Returns:
            Correo validado.

        Raises:
            serializers.ValidationError: Si el correo ya existe.
        """
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        if Usuario.objects.filter(correo=value).exists():
            raise serializers.ValidationError("Este correo ya está registrado.")
        return value

    def create(self, validated_data):
        """Crea Persona, Usuario y auth_user.

        Args:
            validated_data: Datos validados del registro.

        Returns:
            Diccionario con tokens y datos del usuario creado.
        """
        email = validated_data["email"]
        password = validated_data["password"]
        first_name = validated_data["first_name"]
        last_name = validated_data["last_name"]
        phone_number = validated_data["phone_number"]
        role = validated_data["role"]

        # 1. Crear Persona
        persona = Persona.objects.create(
            nombre=first_name,
            apellido_paterno=last_name,
            apellido_materno="",
            fecha_nacimiento="2000-01-01",
            sexo="M",
            domicilio="Sin especificar",
        )

        # 2. Obtener rol
        rol = Rol.objects.get(nombre_rol=role)

        # 3. Crear Usuario (negocio)
        usuario = Usuario.objects.create(
            fk_persona=persona,
            telefono=phone_number,
            correo=email,
            fk_rol=rol,
        )

        # 4. Crear auth_user (Django)
        auth_user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
        )

        # 5. Generar tokens
        refresh = TokenObtainPairSerializer.get_token(auth_user)

        return {
            "success": True,
            "message": "Registro exitoso.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": usuario.id_usuario,
                "email": email,
                "phone_number": phone_number,
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
            },
        }


class MeSerializer(serializers.Serializer):
    """Serializador para obtener datos del usuario autenticado.

    Retorna los datos del usuario actual en el formato que espera
    el frontend (AuthContext.tsx).
    """

    def to_representation(self, instance):
        """Serializa el usuario autenticado.

        Args:
            instance: Objeto Request con el usuario autenticado.

        Returns:
            Diccionario con datos del usuario.
        """
        user = instance.user

        try:
            usuario = Usuario.objects.select_related("fk_rol", "fk_persona").get(
                correo=user.email
            )

            return {
                "id": usuario.id_usuario,
                "email": user.email,
                "phone_number": usuario.telefono,
                "role": usuario.fk_rol.nombre_rol,
                "first_name": usuario.fk_persona.nombre,
                "last_name": (
                    f"{usuario.fk_persona.apellido_paterno} "
                    f"{usuario.fk_persona.apellido_materno}"
                ),
            }
        except Usuario.DoesNotExist:
            return {
                "id": user.id,
                "email": user.email,
                "phone_number": "",
                "role": "Cliente",
                "first_name": "",
                "last_name": "",
            }
