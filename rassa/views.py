from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from rassa.auth_serializers import (
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from rassa.models import Usuario


class RegisterView(generics.CreateAPIView):
    """Endpoint para registrar un nuevo usuario con perfil completo."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        
        # Devolver el usuario recién creado usando UserSerializer
        user_data = UserSerializer(usuario).data
        return Response(
            {
                "success": True,
                "message": "Registro completado exitosamente.",
                "user": user_data,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    """Endpoint para obtener y editar el perfil del usuario autenticado."""

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        try:
            return self.request.user.usuario
        except Usuario.DoesNotExist:
            return None

    def get(self, request):
        usuario = self.get_object()
        if usuario is None:
            return Response(
                {"detail": "El usuario autenticado no tiene un perfil asociado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserSerializer(usuario)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        usuario = self.get_object()
        if usuario is None:
            return Response(
                {"detail": "El usuario autenticado no tiene un perfil asociado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = ProfileUpdateSerializer(usuario, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_usuario = serializer.save()
        
        # Devolver los datos actualizados usando UserSerializer
        return Response(UserSerializer(updated_usuario).data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """Endpoint para cambiar la contraseña del usuario autenticado."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "success": True,
                "message": "Contraseña cambiada exitosamente.",
            },
            status=status.HTTP_200_OK,
        )

