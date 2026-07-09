"""Configuración de rutas URL del proyecto Rassa.

Endpoints disponibles:
    - /admin/              → Panel de administración Django
    - /api/token/          → Login JWT (CustomTokenObtainPairView)
    - /api/token/refresh/  → Refresh token
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from rassa.auth_serializers import CustomTokenObtainPairSerializer
from rassa.views import AuthHealthView, ChangePasswordView, MeView, RegisterView


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login with Spanish error messages."""

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from django.contrib.auth.models import User
        from rassa.models import Log, Usuario

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
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("api/auth/health/", AuthHealthView.as_view(), name="auth_health"),
    path("api/logs/", include("logs.urls")),
]
