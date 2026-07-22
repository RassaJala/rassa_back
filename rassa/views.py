from django.db.models import Q
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
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
    CambiarEstadoSerializer,
    CategoriaProductoSerializer,
    LocalidadSerializer,
    MunicipioSerializer,
    UnidadSerializer,
)
from rassa.models import CategoriaProducto, FamiliaUsuario, Localidad, Log, Municipio, Unidad, Usuario
from rassa.permissions.role_permissions import HasRole, IsAdminOrReadOnly


def _log(user, descripcion, request):
    """Create an audit log entry — failures never break the caller."""
    try:
        Log.objects.create(
            fk_usuario=user.usuario if hasattr(user, "usuario") and user.usuario else None,
            descripcion=descripcion,
            ip=request.META.get("REMOTE_ADDR", ""),
            dispositivo=request.META.get("HTTP_USER_AGENT", "")[:200],
        )
    except Exception:
        pass  # Audit logging must never break the response


def _ok(data=None, message=None, status_code=status.HTTP_200_OK):
    """Standardized success response body with {data, message} envelope."""
    body = {}
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data
    return Response(body, status=status_code)


ok_response = _ok  # Alias for backward compatibility


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

        user = usuario.fk_user
        user_data = UserSerializer(usuario).data

        # Generate JWT so the farmer can access the system immediately
        # NOTE: wrapped in try/except because token generation depends on
        # Redis/blacklist being available. If it fails, the farmer still exists
        # in DB but we return data without tokens (ghost-user prevention).
        try:
            refresh = RefreshToken.for_user(user)
            user_data["access"] = str(refresh.access_token)
            user_data["refresh"] = str(refresh)
        except Exception as exc:
            user_data["access"] = None
            user_data["refresh"] = None
            # Log the failure — token generation was non-fatal
            _log(
                request.user,
                f"Advertencia: tokens JWT no generados para {usuario.correo}: {exc}",
                request,
            )

        _log(request.user, f"Creación de agricultor por admin: {usuario.correo}", request)

        return ok_response(
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
# Permission mixin
# ======================================================================


class CatalogPermissionMixin:
    """Mixin that applies IsAuthenticated for safe methods and Admin-only for writes.

    Use with any DRF generic view or viewset by placing it first in the
    MRO (``class MyView(CatalogPermissionMixin, generics.ListCreateAPIView)``).
    """

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), HasRole("Admin")]


class PublicReadAdminWriteMixin:
    """Mixin for public reads (AllowAny) and admin-only writes.

    Used by catalog endpoints that must be accessible without authentication
    (e.g., municipio/localidad lists for the registration form) but still
    protect mutations behind Admin role.
    """

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), HasRole("Admin")]


# ======================================================================
# Base views for catalog CRUD with admin-only writes + soft-delete
# ======================================================================


class CatalogListCreateView(CatalogPermissionMixin, generics.ListCreateAPIView):
    """Base ListCreate with admin-only writes, _ok wrapping, audit logging, and throttling."""

    pagination_class = None
    throttle_classes = [UserRateThrottle]
    throttle_scope = "catalog_write"
    create_message = "Registro creado exitosamente."

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

    def initial(self, request, *args, **kwargs):
        """Apply ScopedRateThrottle only on write operations."""
        if request.method not in permissions.SAFE_METHODS:
            self.throttle_classes = [ScopedRateThrottle, UserRateThrottle]
        super().initial(request, *args, **kwargs)


class CatalogDetailView(CatalogPermissionMixin, generics.RetrieveUpdateDestroyAPIView):
    """Base detail view with admin-only writes, _ok wrapping, soft-delete, audit logging."""

    throttle_classes = [UserRateThrottle]
    throttle_scope = "catalog_write"
    update_message = "Registro actualizado exitosamente."

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

    def initial(self, request, *args, **kwargs):
        """Apply ScopedRateThrottle only on write operations."""
        if request.method not in permissions.SAFE_METHODS:
            self.throttle_classes = [ScopedRateThrottle, UserRateThrottle]
        super().initial(request, *args, **kwargs)


# ======================================================================
# Municipios y Localidades (catálogos)
# ======================================================================


class MunicipioListCreateView(PublicReadAdminWriteMixin, CatalogListCreateView):
    """List and create municipios (public reads for registration flow, admin-only for write)."""

    queryset = Municipio.objects.filter(estado=True).order_by("nombre")
    serializer_class = MunicipioSerializer
    create_message = "Municipio creado exitosamente."

    # Public reads need a dedicated throttle scope to prevent scraping/DDoS
    throttle_scope = "catalog_read"
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]

    def initial(self, request, *args, **kwargs):
        if request.method not in permissions.SAFE_METHODS:
            self.throttle_scope = "catalog_write"
        super().initial(request, *args, **kwargs)


class MunicipioDetailView(CatalogDetailView):
    """Retrieve, update, or soft-delete a municipio (admin-only for write)."""

    queryset = Municipio.objects.filter(estado=True)
    serializer_class = MunicipioSerializer
    update_message = "Municipio actualizado exitosamente."


class LocalidadByMunicipioListCreateView(PublicReadAdminWriteMixin, CatalogListCreateView):
    """List and create localidades — public reads for registration flow, admin-only for write."""

    serializer_class = LocalidadSerializer
    create_message = "Localidad creada exitosamente."

    # Public reads need a dedicated throttle scope to prevent scraping/DDoS
    throttle_scope = "catalog_read"
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]

    def initial(self, request, *args, **kwargs):
        if request.method not in permissions.SAFE_METHODS:
            self.throttle_scope = "catalog_write"
        super().initial(request, *args, **kwargs)

    def _resolve_municipio_id(self, for_create=False):
        """Extract and validate the municipio ID from URL kwarg or query param.

        Returns the validated integer municipio_id, or raises ValidationError.
        When *for_create* is True the error messages reference ``municipio``
        for the URL-path branch and ``municipio_id`` for the query-param branch,
        matching the existing API contract.
        """
        pk = self.kwargs.get("pk")
        if pk is not None:
            if not Municipio.objects.filter(pk=pk, estado=True).exists():
                raise ValidationError({"municipio": "El municipio especificado no existe o fue eliminado."})
            return int(pk)

        raw = self.request.query_params.get("municipio_id")
        if raw is None:
            raise ValidationError({"municipio_id": "El parámetro municipio_id es requerido."})
        try:
            municipio_id = int(raw)
        except (ValueError, TypeError) as err:
            raise ValidationError({"municipio_id": "municipio_id debe ser un número entero válido."}) from err
        if not Municipio.objects.filter(pk=municipio_id, estado=True).exists():
            raise ValidationError({"municipio_id": "El municipio especificado no existe o fue eliminado."})
        return municipio_id

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
        municipio_id = self._resolve_municipio_id(for_create=True)
        serializer.save(fk_municipio_id=municipio_id)


class LocalidadDetailView(CatalogDetailView):
    """Retrieve, update, or soft-delete a localidad (admin-only for write)."""

    queryset = Localidad.objects.filter(estado=True)
    serializer_class = LocalidadSerializer
    update_message = "Localidad actualizada exitosamente."


# ======================================================================
# Restore endpoint for soft-deleted records
# ======================================================================


class CatalogRestoreView(generics.GenericAPIView):
    """Restore a soft-deleted catalog record (admin-only).

    Subclasses must set ``queryset`` and ``serializer_class``.
    URL: POST /api/{resource}/<pk>/restore/  →  estado = True
    """

    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = "catalog_write"
    soft_delete_field = "estado"

    def get_permissions(self):
        """Admin-only."""
        return [permissions.IsAuthenticated(), HasRole("Admin")]

    def get_queryset(self):
        # Allow access to soft-deleted records for restoration
        return self.queryset.model.objects.filter(estado=False)

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        setattr(instance, self.soft_delete_field, True)
        instance.save(update_fields=[self.soft_delete_field])
        serializer = self.get_serializer(instance)
        model_name = type(instance).__name__
        _log(
            request.user,
            f"{model_name} restaurado: {instance.nombre} (id={instance.pk})",
            request,
        )
        return _ok(data=serializer.data, message="Registro restaurado correctamente.")


class MunicipioRestoreView(CatalogRestoreView):
    queryset = Municipio.objects.all()
    serializer_class = MunicipioSerializer


class LocalidadRestoreView(CatalogRestoreView):
    queryset = Localidad.objects.all()
    serializer_class = LocalidadSerializer


# ======================================================================
# Cambiar estado (activar/desactivar)
# ======================================================================


class CambiarEstadoView(generics.GenericAPIView):
    """PATCH endpoint to toggle active/inactive state for catalog resources.

    Subclasses must set ``queryset`` and ``serializer_class``.
    URL: PATCH /api/{resource}/<pk>/estado/  →  {"estado": true|false}
    """

    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = "catalog_write"

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole("Admin")]

    def get_queryset(self):
        # Include ALL records (including soft-deleted) so we can reactivate
        return self.queryset.model.objects.all()

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        nuevo_estado = serializer.validated_data["estado"]
        instance.estado = nuevo_estado
        instance.save(update_fields=["estado"])

        model_name = type(instance).__name__
        accion = "activado" if nuevo_estado else "desactivado"
        _log(
            request.user,
            f"{model_name} {accion}: {instance.nombre} (id={instance.pk})",
            request,
        )

        output_serializer = self.serializer_class(instance)
        return _ok(
            data=output_serializer.data,
            message=f"{model_name} {accion} exitosamente.",
        )


class MunicipioCambiarEstadoView(CambiarEstadoView):
    queryset = Municipio.objects.all()
    serializer_class = MunicipioSerializer


class LocalidadCambiarEstadoView(CambiarEstadoView):
    queryset = Localidad.objects.all()
    serializer_class = LocalidadSerializer


# ======================================================================
# Trash (papelera — listar inactivos)
# ======================================================================


class CatalogTrashListView(PublicReadAdminWriteMixin, generics.ListAPIView):
    """Base view to list soft-deleted (inactive) catalog records.

    Public reads (AllowAny), admin-only writes (no write actions defined,
    but the mixin is here for consistency with other catalog endpoints).

    Subclasses must set ``queryset``, ``serializer_class``, and ``ordering``.
    URL: GET /api/{resource}/trash/  →  [{...}, ...]

    Note: No pagination (``pagination_class = None``) to match the existing
    ``MunicipioListCreateView`` pattern. If the trash grows large, add
    ``CatalogPagination`` here and update the frontend to read from
    ``results`` inside the paginated envelope.
    """

    pagination_class = None
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = "catalog_read"

    def get_queryset(self):
        return self.queryset.model.objects.filter(estado=False)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)


class MunicipioTrashListView(CatalogTrashListView):
    """List inactive (soft-deleted) municipios."""

    queryset = Municipio.objects.all()
    serializer_class = MunicipioSerializer
    ordering = ["nombre"]


class LocalidadTrashListView(CatalogTrashListView):
    """List inactive (soft-deleted) localidades."""

    queryset = Localidad.objects.all()
    serializer_class = LocalidadSerializer
    ordering = ["nombre"]


# ======================================================================
# Permanent delete (hard delete desde la BD)
# ======================================================================


class CatalogPermanentDeleteView(generics.GenericAPIView):
    """Base view to permanently delete a soft-deleted catalog record.

    Subclasses must set ``queryset``.
    URL: POST /api/{resource}/<pk>/permanent/  →  hard delete
    """

    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = "catalog_write"

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole("Admin")]

    def get_queryset(self):
        # Only allow permanent delete on already-inactive records
        return self.queryset.model.objects.filter(estado=False)

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        model_name = type(instance).__name__
        nombre = getattr(instance, "nombre", "")
        pk = instance.pk
        instance.delete()
        _log(
            request.user,
            f"{model_name} eliminado permanentemente: {nombre} (id={pk})",
            request,
        )
        return _ok(message="Registro eliminado permanentemente.")


class MunicipioPermanentDeleteView(CatalogPermanentDeleteView):
    """Permanently delete a soft-deleted municipio.

    Blocks deletion if the municipio still has associated localidades
    (even inactive ones) to prevent accidental CASCADE data loss.
    """

    queryset = Municipio.objects.all()

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        if Localidad.objects.filter(fk_municipio=instance).exists():
            raise ValidationError(
                {
                    "non_field_errors": [
                        "No se puede eliminar el municipio porque tiene localidades asociadas. "
                        "Elimine o reasigne las localidades primero."
                    ]
                }
            )
        return super().post(request, *args, **kwargs)


class LocalidadPermanentDeleteView(CatalogPermanentDeleteView):
    """Permanently delete a soft-deleted localidad."""

    queryset = Localidad.objects.all()


class SearchUsersView(APIView):
    """Endpoint para buscar usuarios activos por nombre o correo."""

    permission_classes = [permissions.IsAuthenticated, HasRole("Admin")]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 1:
            return _ok(data=[])

        include_assigned = request.query_params.get("include_assigned", "false").lower() in ["true", "1"]

        base_query = (
            Usuario.objects.filter(estado=True)
            .exclude(fk_rol__nombre_rol="Admin")
            .filter(
                Q(correo__icontains=query)
                | Q(fk_persona__nombre__icontains=query)
                | Q(fk_persona__apellido_paterno__icontains=query)
                | Q(fk_persona__apellido_materno__icontains=query)
            )
        )

        if not include_assigned:
            usuarios_con_familia = FamiliaUsuario.objects.filter(
                estado=True, fk_familia__estado=True
            ).values_list("fk_usuario_id", flat=True)
            base_query = base_query.exclude(id_usuario__in=usuarios_con_familia)

        usuarios = base_query[:10]
        serializer = UserSerializer(usuarios, many=True)
        return _ok(data=serializer.data)
