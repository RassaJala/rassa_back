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
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from logs.utils import get_client_ip
from rassa.auth_serializers import CustomTokenObtainPairSerializer
from rassa.models import Log, Usuario
from rassa.productos_views import (
    CategoriaListView,
    ProductoDetailView,
    ProductoImagenDeleteView,
    ProductoImagenUploadView,
    ProductoListView,
    UnidadListView,
)
from rassa.views import (
    AuthHealthView,
    ChangePasswordView,
    LocalidadByMunicipioListView,
    MeView,
    MunicipioListView,
    RegisterView,
)

logger = logging.getLogger(__name__)


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
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("api/auth/health/", AuthHealthView.as_view(), name="auth_health"),
    path("api/logs/", include("logs.urls")),
    path("api/municipios/", MunicipioListView.as_view(), name="municipios"),
    path("api/localidades/", LocalidadByMunicipioListView.as_view(), name="localidades"),
    path("api/productos/", ProductoListView.as_view(), name="producto_list"),
    path("api/productos/<int:pk>/", ProductoDetailView.as_view(), name="producto_detail"),
    path("api/productos/<int:pk>/imagen/", ProductoImagenUploadView.as_view(), name="producto_imagen"),
    path("api/productos/<int:pk>/imagen/<int:id_imagen>/", ProductoImagenDeleteView.as_view(), name="producto_imagen_delete"),
    path("api/categorias/", CategoriaListView.as_view(), name="categoria_list"),
    path("api/unidades/", UnidadListView.as_view(), name="unidad_list"),
]
