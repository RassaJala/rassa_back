from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from rassa.auth_serializers import (
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from rassa.models import Log, Usuario


def _log(user, descripcion, request):
    """Create an audit log entry."""
    Log.objects.create(
        fk_usuario=user.usuario if hasattr(user, "usuario") and user.usuario else None,
        descripcion=descripcion,
        ip=request.META.get("REMOTE_ADDR", ""),
        dispositivo=request.META.get("HTTP_USER_AGENT", "")[:200],
    )


def _ok(data=None, message=None, status_code=status.HTTP_200_OK):
    """Standardized success response."""
    body = {}
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data
    return Response(body, status=status_code)


class RegisterView(generics.CreateAPIView):
    """Endpoint para registrar un nuevo usuario con perfil completo.

    Devuelve el usuario creado junto con tokens JWT (access + refresh).
    """

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        # Generar tokens JWT
        user = usuario.fk_user
        refresh = RefreshToken.for_user(user)

        user_data = UserSerializer(usuario).data
        user_data["access"] = str(refresh.access_token)
        user_data["refresh"] = str(refresh)

        _log(user, f"Registro de usuario: {usuario.correo} (rol: {usuario.fk_rol})", request)

        return _ok(
            data=user_data,
            message="Registro completado exitosamente.",
            status_code=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    """Endpoint para obtener y editar el perfil del usuario autenticado."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "user"

    def get_object(self):
        try:
            return self.request.user.usuario
        except Usuario.DoesNotExist as err:
            raise NotFound("El usuario autenticado no tiene un perfil asociado.") from err

    def get(self, request):
        usuario = self.get_object()
        serializer = UserSerializer(usuario)
        return _ok(data=serializer.data)

    def patch(self, request):
        usuario = self.get_object()

        serializer = ProfileUpdateSerializer(usuario, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_usuario = serializer.save()

        _log(request.user, f"Actualización de perfil: {usuario.correo}", request)

        return _ok(data=UserSerializer(updated_usuario).data, message="Perfil actualizado exitosamente.")


class ChangePasswordView(APIView):
    """Endpoint para cambiar la contraseña del usuario autenticado."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "change_password"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        _log(request.user, "Cambio de contraseña", request)

        return _ok(message="Contraseña cambiada exitosamente.")
