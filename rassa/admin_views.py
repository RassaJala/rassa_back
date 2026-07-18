from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from rassa.admin_serializers import AdminUserSerializer, AdminUserUpdateSerializer
from rassa.auth_serializers import ROLE_REVERSE_MAPPING
from rassa.models import Usuario
from rassa.permissions.role_permissions import HasRole
from rassa.views import _log, _ok

ADMIN = "Admin"
ADMIN_ROLE_KEY = ROLE_REVERSE_MAPPING[ADMIN]
ADMIN_PAGE_SIZE = 20
MAX_SEARCH_LENGTH = 100


class AdminUsuarioPagination(PageNumberPagination):
    page_size = ADMIN_PAGE_SIZE


def _get_active_admin_count():
    """Count active admins with row-level locking to prevent TOCTOU races."""
    return Usuario.objects.select_for_update().filter(fk_rol__nombre_rol=ADMIN, estado=True).count()


def _ensure_single_admin_protected(usuario):
    """Return Response if action would leave zero active admins, else None.

    Must be called inside a transaction.atomic() block with select_for_update.
    """
    if usuario.fk_rol and usuario.fk_rol.nombre_rol == ADMIN:
        if _get_active_admin_count() <= 1:
            return Response(
                {"detail": "No se puede alterar al único administrador activo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    return None


class AdminUsuarioViewSet(viewsets.GenericViewSet):
    """Endpoints administrativos para gestionar usuarios.

    Solo accesible por usuarios con rol Admin.

    Acciones:
        list     GET    /api/admin/usuarios/
        retrieve GET    /api/admin/usuarios/{id}/
        update   PATCH  /api/admin/usuarios/{id}/
        toggle   PATCH  /api/admin/usuarios/{id}/toggle-estado/
    """

    pagination_class = AdminUsuarioPagination

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(ADMIN)]

    def list(self, request):
        """Listar usuarios con búsqueda y filtros.

        Query params:
            search  — Busca en nombre, apellido_paterno, apellido_materno, correo
            rol     — Filtra por nombre de rol
            estado  — Filtra por estado (true/false)
        """
        queryset = Usuario.objects.select_related("fk_persona", "fk_rol", "fk_persona__fk_localidad").all()

        search = request.query_params.get("search")
        if search:
            if len(search) > MAX_SEARCH_LENGTH:
                return _ok(data={"count": 0, "next": None, "previous": None, "results": []})
            queryset = queryset.filter(
                Q(correo__icontains=search)
                | Q(fk_persona__nombre__icontains=search)
                | Q(fk_persona__apellido_paterno__icontains=search)
                | Q(fk_persona__apellido_materno__icontains=search)
            )

        rol = request.query_params.get("rol")
        if rol:
            queryset = queryset.filter(fk_rol__nombre_rol__icontains=rol)

        estado = request.query_params.get("estado")
        if estado is not None and estado != "":
            estado_bool = estado.lower() == "true"
            queryset = queryset.filter(estado=estado_bool)

        queryset = queryset.order_by("id_usuario")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = AdminUserSerializer(page, many=True)
            paginated = self.paginator.get_paginated_response(serializer.data).data
            return _ok(data=paginated)

        serializer = AdminUserSerializer(queryset, many=True)
        return _ok(data=serializer.data)

    def retrieve(self, request, pk=None):
        """Obtener detalle de un usuario específico."""
        try:
            usuario = Usuario.objects.select_related("fk_persona", "fk_rol", "fk_persona__fk_localidad").get(pk=pk)
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUserSerializer(usuario)
        return _ok(data=serializer.data)

    def partial_update(self, request, pk=None):
        """Editar datos de un usuario (teléfono, nombre, rol, etc.)."""
        admin_usuario = request.user.usuario
        try:
            with transaction.atomic():
                usuario = Usuario.objects.select_related("fk_persona", "fk_rol").select_for_update().get(pk=pk)

                if usuario.id_usuario == admin_usuario.id_usuario and "role" in request.data:
                    return Response(
                        {"detail": "No puedes cambiar tu propio rol de administrador."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if "role" in request.data and request.data["role"] != ADMIN_ROLE_KEY:
                    blocked = _ensure_single_admin_protected(usuario)
                    if blocked:
                        return blocked

                serializer = AdminUserUpdateSerializer(usuario, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                updated = serializer.save()
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except IntegrityError:
            return Response(
                {"detail": "Error de integridad al guardar."},
                status=status.HTTP_409_CONFLICT,
            )

        _log(
            request.user,
            f"Actualización de usuario: {updated.correo} por admin {admin_usuario.correo}",
            request,
        )
        return _ok(
            data=AdminUserSerializer(updated).data,
            message="Usuario actualizado exitosamente.",
        )

    @action(detail=True, methods=["patch"], url_path="toggle-estado")
    def toggle_estado(self, request, pk=None):
        """Activar o desactivar un usuario."""
        try:
            with transaction.atomic():
                usuario = Usuario.objects.select_related("fk_rol").select_for_update().get(pk=pk)

                admin_usuario = request.user.usuario
                if usuario.id_usuario == admin_usuario.id_usuario and usuario.estado:
                    return Response(
                        {"detail": "No puedes desactivar tu propia cuenta de administrador."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if usuario.estado:
                    blocked = _ensure_single_admin_protected(usuario)
                    if blocked:
                        return blocked

                usuario.estado = not usuario.estado
                usuario.save(update_fields=["estado"])
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        accion = "activado" if usuario.estado else "desactivado"
        _log(
            request.user,
            f"Usuario {accion}: {usuario.correo} por admin {admin_usuario.correo}",
            request,
        )
        return _ok(
            data=AdminUserSerializer(usuario).data,
            message=f"Usuario {accion} exitosamente.",
        )
