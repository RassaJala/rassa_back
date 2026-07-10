"""Configuración de rutas URL del proyecto Rassa.

Endpoints disponibles:
    - /admin/              → Panel de administración Django
    - /api/token/          → Login JWT (CustomTokenObtainPairView)
    - /api/token/refresh/  → Refresh token
"""

import logging

from django.contrib import admin
from django.urls import include, path
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from logs.utils import get_client_ip
from rassa.auth_serializers import CustomTokenObtainPairSerializer
from rassa.models import Log, Usuario
from rassa.views import AuthHealthView, ChangePasswordView, RegisterView

logger = logging.getLogger(__name__)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def auth_me(request):
    usuario = Usuario.objects.filter(fk_user=request.user).select_related("fk_persona", "fk_rol").first()
    persona = usuario.fk_persona if usuario else None

    if request.method == "PATCH":
        if persona:
            if "nombre" in request.data:
                persona.nombre = request.data["nombre"]
            if "apellidos" in request.data:
                persona.apellido_paterno = request.data["apellidos"]
            if "fecha_nacimiento" in request.data:
                persona.fecha_nacimiento = request.data["fecha_nacimiento"]
            if "direccion" in request.data:
                persona.domicilio = request.data["direccion"]
            persona.save()
        return Response(
            {
                "id": request.user.id,
                "nombre": persona.nombre if persona else None,
                "apellidos": persona.apellido_paterno if persona else None,
                "email": request.user.email,
                "fecha_nacimiento": str(persona.fecha_nacimiento) if persona else None,
                "direccion": persona.domicilio if persona else None,
            }
        )

    data = {
        "id": request.user.id,
        "email": request.user.email,
        "username": request.user.username,
    }
    if usuario:
        data.update(
            {
                "id_usuario": usuario.id_usuario,
                "telefono": usuario.telefono,
                "rol": usuario.fk_rol.nombre_rol if usuario.fk_rol else None,
                "nombre": f"{persona.nombre} {persona.apellido_paterno}" if persona else None,
            }
        )
    return Response(data)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login with Spanish error messages."""

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        email = request.data.get("email")

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            try:
                Log.objects.create(
                    fk_usuario=None,
                    descripcion=f"login_fallido POST /api/token/ email={email}",
                    ip=get_client_ip(request),
                    dispositivo=request.META.get("HTTP_USER_AGENT", ""),
                )
            except Exception as log_exc:
                logger.warning("Error al guardar log de login fallido: %s", log_exc)
            raise

        # Use serializer.user (validated during is_valid) instead of re-querying — avoids TOCTOU race
        user = getattr(serializer, "user", None)
        usuario = Usuario.objects.filter(fk_user=user).first() if user else None
        try:
            Log.objects.create(
                fk_usuario=usuario,
                descripcion="login POST /api/token/",
                ip=get_client_ip(request),
                dispositivo=request.META.get("HTTP_USER_AGENT", ""),
            )
        except Exception as log_exc:
            logger.warning("Error al guardar log de login exitoso: %s", log_exc)

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/me/", auth_me, name="auth_me"),
    path("api/auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("api/auth/health/", AuthHealthView.as_view(), name="auth_health"),
    path("api/logs/", include("logs.urls")),
]
