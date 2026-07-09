"""Configuración de rutas URL del proyecto Rassa.

Endpoints disponibles:
    - /admin/              → Panel de administración Django
    - /api/token/          → Login JWT (CustomTokenObtainPairView)
    - /api/token/refresh/  → Refresh token
"""

from django.contrib import admin
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.urls import include, path
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from rassa.auth_serializers import CustomTokenObtainPairSerializer
from rassa.models import Log, Usuario


@api_view(["GET"])
def auth_me(request):
    usuario = Usuario.objects.filter(fk_user=request.user).select_related("fk_persona", "fk_rol").first()
    data = {
        "id": request.user.id,
        "email": request.user.email,
        "username": request.user.username,
    }
    if usuario:
        data.update({
            "id_usuario": usuario.id_usuario,
            "telefono": usuario.telefono,
            "rol": usuario.fk_rol.nombre_rol if usuario.fk_rol else None,
            "nombre": f"{usuario.fk_persona.nombre} {usuario.fk_persona.apellido_paterno}" if usuario.fk_persona else None,
        })
    return Response(data)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login with Spanish error messages."""

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = request.data.get("email")
        user = User.objects.filter(email=email).first()
        usuario = Usuario.objects.filter(fk_user=user).first() if user else None
        Log.objects.create(
            fk_usuario=usuario,
            descripcion="login POST /api/token/",
            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
            dispositivo=request.META.get("HTTP_USER_AGENT", ""),
        )

        return JsonResponse(serializer.validated_data, status=status.HTTP_200_OK)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", auth_me, name="auth_me"),
    path("api/logs/", include("logs.urls")),
]
