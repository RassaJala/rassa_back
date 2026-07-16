from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from rassa.auth_serializers import (
    AdminCreateAgricultorSerializer,
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)
from rassa.catalogos_serializers import (
    CategoriaProductoSerializer,
    LocalidadSerializer,
    MunicipioSerializer,
    UnidadSerializer,
)
from rassa.models import CategoriaProducto, Localidad, Log, Municipio, Unidad, Usuario
from rassa.permissions.role_permissions import HasRole, IsAdminOrReadOnly


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


# Alias for base branch compatibility — main uses ok_response, not _ok
ok_response = _ok


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


class AdminCreateAgricultorView(generics.CreateAPIView):
    """Endpoint exclusivo para que un Admin cree usuarios Agricultor.

    Solo accesible por usuarios con rol Admin.
    No require que el agricultor se registre por sí mismo.
    """

    serializer_class = AdminCreateAgricultorSerializer
    permission_classes = [permissions.IsAuthenticated, HasRole("Admin")]
    throttle_scope = "admin_write"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        # Generate JWT so the farmer can access the system immediately
        user = usuario.fk_user
        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(usuario).data
        user_data["access"] = str(refresh.access_token)
        user_data["refresh"] = str(refresh)

        _log(request.user, f"Creación de agricultor por admin: {usuario.correo}", request)

        return _ok(
            data=user_data,
            message="Agricultor creado exitosamente.",
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
    """Endpoint para cambiar la contraseña del usuario autenticado.

    Si se incluye un `refresh_token` en el cuerpo, se invalida (lista negra)
    para que el token anterior deje de funcionar.

    Nota: Los tokens access existentes siguen siendo válidos hasta su expiración
    natural (2 horas por defecto). Para invalidación completa se requiere
    rotación de tokens del lado del cliente.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "change_password"

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Blacklist the refresh token if provided
        refresh_token_str = request.data.get("refresh_token")
        if refresh_token_str:
            try:
                token = RefreshToken(refresh_token_str)
                token.blacklist()
            except Exception:
                pass  # Invalid token — just skip blacklisting

        _log(request.user, "Cambio de contraseña", request)

        return _ok(message="Contraseña cambiada exitosamente.")


class AuthHealthView(APIView):
    """Health check para el subsistema de autenticación."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return _ok(message="ok")


class CatalogPagination(PageNumberPagination):
    page_size = 20


class CatalogViewSet(viewsets.ModelViewSet):
    """ViewSet base para catálogos con respuestas envueltas en un formato consistente."""

    permission_classes = [IsAdminOrReadOnly]
    pagination_class = CatalogPagination
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]

    def initial(self, request, *args, **kwargs):
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.throttle_scope = "catalog_write"
        super().initial(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return _ok(data=response.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            return _ok(
                data=response.data,
                message="Registro creado correctamente.",
                status_code=status.HTTP_201_CREATED,
            )
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            return _ok(data=response.data, message="Registro actualizado correctamente.")
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return _ok(message="Registro eliminado correctamente.")

    def perform_destroy(self, instance):
        instance.estado = False
        instance.save(update_fields=["estado"])


class CategoriaProductoViewSet(CatalogViewSet):
    queryset = CategoriaProducto.objects.filter(estado=True).order_by("id_categoria")
    serializer_class = CategoriaProductoSerializer


class UnidadViewSet(CatalogViewSet):
    queryset = Unidad.objects.filter(estado=True).order_by("id_unidad")
    serializer_class = UnidadSerializer


# ======================================================================
# Municipios y Localidades (catálogos)
# ======================================================================


class MunicipioListView(generics.ListAPIView):
    """List all municipios (public — no auth required for registration flow)."""

    queryset = Municipio.objects.all().order_by("nombre")
    serializer_class = MunicipioSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)


class LocalidadByMunicipioListView(APIView):
    """List localidades for a given municipio (public — no auth required for registration flow)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        raw = request.query_params.get("municipio_id")

        if not raw:
            raise ValidationError({"municipio_id": "El parámetro municipio_id es requerido."})

        try:
            municipio_id = int(raw)
        except (ValueError, TypeError) as err:
            raise ValidationError({"municipio_id": "municipio_id debe ser un número entero válido."}) from err

        localidades = Localidad.objects.filter(fk_municipio_id=municipio_id).order_by("nombre")
        serializer = LocalidadSerializer(localidades, many=True)
        return _ok(data=serializer.data)
