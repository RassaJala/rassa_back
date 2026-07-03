"""Vistas de autenticación para el frontend.

Vistas diseñadas para ser consumidas por el AuthContext.tsx del frontend
React Native. Retornan el formato exacto que espera el cliente.

Endpoints:
    - LoginView: POST /api/auth/login-api/
    - RegisterView: POST /api/auth/register/
    - MeView: GET /api/auth/me/

Referencia:
    Documento Técnico v3, Fase 13.4 - Módulo M3 (Usuarios y Roles).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, RegisterSerializer, MeSerializer


class LoginView(APIView):
    """Vista de login para el frontend.

    Autentica al usuario con email y contraseña, retorna tokens JWT
    y datos del usuario en el formato que espera AuthContext.tsx.

    Method: POST
    Body: {"email": "...", "password": "...", "remember": false}
    Response 200:
        {
            "success": true,
            "message": "Inicio de sesión exitoso.",
            "remember": false,
            "access": "jwt...",
            "refresh": "jwt...",
            "user": {...}
        }
    Response 400:
        {
            "success": false,
            "message": "No existe una cuenta con este correo."
        }
    """

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        """Ejecuta el login del usuario.

        Args:
            request: Objeto Request con email, password y remember.

        Returns:
            Response con tokens JWT y datos del usuario.
        """
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.validated_data
            return Response(
                {
                    "success": data["success"],
                    "message": data["message"],
                    "remember": request.data.get("remember", False),
                    "access": data["access"],
                    "refresh": data["refresh"],
                    "user": data["user_data"],
                },
                status=status.HTTP_200_OK,
            )

        # Retornar primer error encontrado
        errors = serializer.errors
        if "non_field_errors" in errors:
            error_msg = errors["non_field_errors"][0]
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", "Error de autenticación.")
        elif "email" in errors:
            error_msg = errors["email"][0]
        elif "password" in errors:
            error_msg = errors["password"][0]
        else:
            error_msg = "Error de autenticación."

        return Response(
            {"success": False, "message": str(error_msg)},
            status=status.HTTP_400_BAD_REQUEST,
        )


class RegisterView(APIView):
    """Vista de registro para el frontend.

    Crea un nuevo usuario con sus datos personales y credenciales.
    Retorna tokens JWT y datos del usuario registrado.

    Method: POST
    Body:
        {
            "email": "...",
            "password": "...",
            "first_name": "...",
            "last_name": "...",
            "phone_number": "...",
            "role": "buyer"
        }
    Response 201:
        {
            "success": true,
            "message": "Registro exitoso.",
            "access": "jwt...",
            "refresh": "jwt...",
            "user": {...}
        }
    """

    permission_classes = []
    authentication_classes = []

    def post(self, request):
        """Registra un nuevo usuario.

        Args:
            request: Objeto Request con datos del registro.

        Returns:
            Response con tokens JWT y datos del usuario creado.
        """
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.save()
            return Response(data, status=status.HTTP_201_CREATED)

        # Retornar errores
        errors = serializer.errors
        error_msg = "Error en el registro."
        if "email" in errors:
            error_msg = errors["email"][0]
        elif "non_field_errors" in errors:
            error_msg = errors["non_field_errors"][0]

        return Response(
            {"success": False, "message": str(error_msg)},
            status=status.HTTP_400_BAD_REQUEST,
        )


class MeView(APIView):
    """Vista para obtener datos del usuario autenticado.

    Retorna los datos del usuario actual en el formato que espera
    el frontend (AuthContext.tsx).

    Method: GET
    Headers: Authorization: Bearer <access_token>
    Response 200:
        {
            "id": 1,
            "email": "...",
            "phone_number": "...",
            "role": "buyer",
            "first_name": "...",
            "last_name": "..."
        }
    Response 401:
        {"detail": "Authentication credentials were not provided."}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Obtiene datos del usuario autenticado.

        Args:
            request: Objeto Request con usuario autenticado.

        Returns:
            Response con datos del usuario.
        """
        serializer = MeSerializer()
        data = serializer.to_representation(request)
        return Response(data, status=status.HTTP_200_OK)
