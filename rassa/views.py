from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from rassa.auth_serializers import (
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
    """Standardized success response body with {data, message} envelope."""
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
    """ViewSet base para catálogos con respuestas envueltas en un formato consistente.

    Incluye endpoints de papelera:
        - GET  /{prefix}/trash/           → Lista registros desactivados
        - POST /{pk}/restore/             → Restaura un registro desactivado
        - DELETE /{pk}/permanent/          → Eliminación permanente (hard delete)
    """

    permission_classes = [IsAdminOrReadOnly]
    pagination_class = CatalogPagination
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    soft_delete_field = "estado"

    def get_queryset(self):
        model = self.queryset.model
        if self.action == "trash":
            return model.objects.filter(estado=False).order_by("-creado_en")
        if self.action in ("restore", "permanent"):
            return model.objects.filter(estado=False)
        return model.objects.filter(estado=True)

    def initial(self, request, *args, **kwargs):
        if self.action in ("create", "update", "partial_update", "destroy", "permanent"):
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
        setattr(instance, self.soft_delete_field, False)
        instance.save(update_fields=[self.soft_delete_field])

    @action(detail=False, methods=["get"], url_path="trash")
    def trash(self, request, *args, **kwargs):
        """Lista registros desactivados (papelera)."""
        return self.list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None, *args, **kwargs):
        """Restaura un registro desactivado."""
        instance = self.get_object()
        setattr(instance, self.soft_delete_field, True)
        instance.save(update_fields=[self.soft_delete_field])
        serializer = self.get_serializer(instance)
        return _ok(data=serializer.data, message="Registro restaurado correctamente.")

    @action(detail=True, methods=["post"], url_path="permanent")
    def permanent(self, request, pk=None, *args, **kwargs):
        """Eliminación permanente de un registro desactivado."""
        instance = self.get_object()
        instance.delete()
        return _ok(message="Registro eliminado permanentemente.")


class CategoriaProductoViewSet(CatalogViewSet):
    queryset = CategoriaProducto.objects.all()
    serializer_class = CategoriaProductoSerializer


class UnidadViewSet(CatalogViewSet):
    queryset = Unidad.objects.all()
    serializer_class = UnidadSerializer


# ======================================================================
# Base views for catalog CRUD with admin-only writes + soft-delete
# ======================================================================


class CatalogListCreateView(generics.ListCreateAPIView):
    """Base ListCreate with admin-only writes, _ok wrapping, audit logging, and throttling."""

    pagination_class = None
    throttle_classes = [UserRateThrottle]
    create_message = "Registro creado exitosamente."

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), HasRole("Admin")]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        model_name = type(serializer.instance).__name__ if serializer.instance else "Registro"
        nombre = getattr(serializer.instance, "nombre", "")
        _log(request.user, f"{model_name} creado: {nombre} (id={serializer.instance.pk})", request)
        return _ok(
            data=serializer.data,
            message=self.create_message,
            status_code=status.HTTP_201_CREATED,
        )


class CatalogDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Base detail view with admin-only writes, _ok wrapping, soft-delete, audit logging."""

    throttle_classes = [UserRateThrottle]
    update_message = "Registro actualizado exitosamente."

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), HasRole("Admin")]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return _ok(data=serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        model_name = type(instance).__name__
        _log(request.user, f"{model_name} actualizado: {instance.nombre} (id={instance.pk})", request)
        return _ok(data=serializer.data, message=self.update_message)

    def perform_destroy(self, instance):
        instance.estado = False
        instance.save(update_fields=["estado"])
        model_name = type(instance).__name__
        _log(self.request.user, f"{model_name} eliminado (soft): {instance.nombre} (id={instance.pk})", self.request)


# ======================================================================
# Municipios y Localidades (catálogos)
# ======================================================================


class MunicipioListCreateView(CatalogListCreateView):
    """List and create municipios (admin-only for write)."""

    queryset = Municipio.objects.filter(estado=True).order_by("nombre")
    serializer_class = MunicipioSerializer
    create_message = "Municipio creado exitosamente."


class MunicipioDetailView(CatalogDetailView):
    """Retrieve, update, or soft-delete a municipio (admin-only for write)."""

    queryset = Municipio.objects.filter(estado=True)
    serializer_class = MunicipioSerializer
    update_message = "Municipio actualizado exitosamente."


class LocalidadByMunicipioListCreateView(CatalogListCreateView):
    """List and create localidades — via nested URL or backward compat query param."""

    serializer_class = LocalidadSerializer
    create_message = "Localidad creada exitosamente."

    def get_queryset(self):
        base = Localidad.objects.filter(estado=True)
        pk = self.kwargs.get("pk")
        if pk is not None:
            return base.filter(fk_municipio_id=pk).order_by("nombre")
        raw = self.request.query_params.get("municipio_id")
        if raw is not None:
            try:
                municipio_id = int(raw)
            except (ValueError, TypeError) as err:
                raise ValidationError({"municipio_id": "municipio_id debe ser un número entero válido."}) from err
            return base.filter(fk_municipio_id=municipio_id).order_by("nombre")
        raise ValidationError({"municipio_id": "El parámetro municipio_id es requerido."})

    def perform_create(self, serializer):
        pk = self.kwargs.get("pk")
        if pk is not None:
            if not Municipio.objects.filter(pk=pk, estado=True).exists():
                raise ValidationError(
                    {"municipio": "El municipio especificado no existe o fue eliminado."}
                )
            serializer.save(fk_municipio_id=pk)
            return
        raw = self.request.query_params.get("municipio_id")
        if raw is None:
            raise ValidationError({"municipio_id": "El parámetro municipio_id es requerido."})
        try:
            municipio_id = int(raw)
        except (ValueError, TypeError) as err:
            raise ValidationError({"municipio_id": "municipio_id debe ser un número entero válido."}) from err
        if not Municipio.objects.filter(pk=municipio_id, estado=True).exists():
            raise ValidationError({"municipio_id": "El municipio especificado no existe o fue eliminado."})
        serializer.save(fk_municipio_id=municipio_id)


class LocalidadDetailView(CatalogDetailView):
    """Retrieve, update, or soft-delete a localidad (admin-only for write)."""

    queryset = Localidad.objects.filter(estado=True)
    serializer_class = LocalidadSerializer
    update_message = "Localidad actualizada exitosamente."
