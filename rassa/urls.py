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
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from logs.utils import get_client_ip
from rassa.admin_views import AdminUsuarioViewSet
from rassa.auth_serializers import CustomTokenObtainPairSerializer
from rassa.blueprints.chat.urls import urlpatterns as chat_urls
from rassa.blueprints.familias.urls import urlpatterns as familias_urls
from rassa.blueprints.publicacion.urls import urlpatterns as publicacion_urls
from rassa.models import Log, Usuario
from rassa.pedidos_views import PedidoHistorialView
from rassa.views import (
    AdminCreateAgricultorView,
    AuthHealthView,
    CategoriaProductoViewSet,
    ChangePasswordView,
    LocalidadByMunicipioListCreateView,
    LocalidadCambiarEstadoView,
    LocalidadDetailView,
    LocalidadPermanentDeleteView,
    LocalidadRestoreView,
    LocalidadTrashListView,
    MeView,
    MunicipioCambiarEstadoView,
    MunicipioDetailView,
    MunicipioListCreateView,
    MunicipioPermanentDeleteView,
    MunicipioRestoreView,
    MunicipioTrashListView,
    RegisterView,
    SearchUsersView,
    UnidadViewSet,
)

logger = logging.getLogger(__name__)

router = DefaultRouter()
router.register(r"api/categorias", CategoriaProductoViewSet, basename="categoria-producto")
router.register(r"api/unidades", UnidadViewSet, basename="unidad")
router.register(r"api/admin/usuarios", AdminUsuarioViewSet, basename="admin-usuarios")


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
    path("api/auth/create-farmer/", AdminCreateAgricultorView.as_view(), name="create-farmer"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/auth/search-users/", SearchUsersView.as_view(), name="search-users"),
    path("api/auth/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("api/auth/health/", AuthHealthView.as_view(), name="auth_health"),
    path("api/pedidos/<int:pk>/historial/", PedidoHistorialView.as_view(), name="pedido-historial"),
    path("api/logs/", include("logs.urls")),
    path("api/municipios/", MunicipioListCreateView.as_view(), name="municipios"),
    path("api/municipios/trash/", MunicipioTrashListView.as_view(), name="municipios-trash"),
    path("api/municipios/<int:pk>/", MunicipioDetailView.as_view(), name="municipio-detail"),
    path("api/municipios/<int:pk>/restore/", MunicipioRestoreView.as_view(), name="municipio-restore"),
    path(
        "api/municipios/<int:pk>/estado/",
        MunicipioCambiarEstadoView.as_view(),
        name="municipio-cambiar-estado",
    ),
    path(
        "api/municipios/<int:pk>/permanent/",
        MunicipioPermanentDeleteView.as_view(),
        name="municipio-permanent",
    ),
    path(
        "api/municipios/<int:pk>/localidades/",
        LocalidadByMunicipioListCreateView.as_view(),
        name="localidades-by-municipio",
    ),
    path("api/localidades/", LocalidadByMunicipioListCreateView.as_view(), name="localidades"),
    path("api/localidades/trash/", LocalidadTrashListView.as_view(), name="localidades-trash"),
    path("api/localidades/<int:pk>/", LocalidadDetailView.as_view(), name="localidad-detail"),
    path("api/localidades/<int:pk>/restore/", LocalidadRestoreView.as_view(), name="localidad-restore"),
    path(
        "api/localidades/<int:pk>/estado/",
        LocalidadCambiarEstadoView.as_view(),
        name="localidad-cambiar-estado",
    ),
    path(
        "api/localidades/<int:pk>/permanent/",
        LocalidadPermanentDeleteView.as_view(),
        name="localidad-permanent",
    ),
    path("", include(router.urls)),
    path("", include(publicacion_urls)),
    path("", include(chat_urls)),
    path("", include(familias_urls)),
]
