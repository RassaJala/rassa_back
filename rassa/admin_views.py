from django.db import transaction
from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from rassa.admin_serializers import AdminUserSerializer, AdminUserUpdateSerializer
from rassa.models import Usuario
from rassa.permissions.role_permissions import HasRole
from rassa.views import _log, _ok

ADMIN = "Admin"


class AdminUsuarioPagination(PageNumberPagination):
    page_size = 20


class AdminUsuarioViewSet(viewsets.ViewSet):
    """Endpoints administrativos para gestionar usuarios.

    Solo accesible por usuarios con rol Admin.

    Acciones:
        list     GET    /api/admin/usuarios/          â€" Listar con filtros
        retrieve GET    /api/admin/usuarios/{id}/     â€" Detalle de usuario
        update   PATCH  /api/admin/usuarios/{id}/     â€" Editar datos
        toggle   PATCH  /api/admin/usuarios/{id}/toggle-estado/ â€" Activar/desactivar
    """

    pagination_class = AdminUsuarioPagination

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(ADMIN)]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        paginated = self.paginator.get_paginated_response(data).data
        return _ok(data=paginated)

    def list(self, request):
        """Listar usuarios con bÃºsqueda y filtros.

        Query params:
            search  â€” Busca en nombre, apellido_paterno, apellido_materno, correo
            rol     â€” Filtra por nombre de rol (Admin, Agricultor, Vendedor, Cliente)
            estado  â€” Filtra por estado (true/false)
        """
        queryset = Usuario.objects.select_related("fk_persona", "fk_rol", "fk_persona__fk_localidad").all()

        search = request.query_params.get("search")
        if search:
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
            return self.get_paginated_response(serializer.data)

        serializer = AdminUserSerializer(queryset, many=True)
        return _ok(data=serializer.data)

    def retrieve(self, request, pk=None):
        """Obtener detalle de un usuario especÃ­fico."""
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
        """Editar datos de un usuario (telÃ©fono, nombre, rol, etc.)."""
        admin_usuario = request.user.usuario
        try:
            with transaction.atomic():
                usuario = Usuario.objects.select_related("fk_persona", "fk_rol").select_for_update().get(pk=pk)

                if usuario.id_usuario == admin_usuario.id_usuario and "role" in request.data:
                    return Response(
                        {"detail": "No puedes cambiar tu propio rol de administrador."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if "role" in request.data:
                    new_role = request.data["role"]
                    if usuario.fk_rol and usuario.fk_rol.nombre_rol == ADMIN and new_role != "admin":
                        active_admin_count = Usuario.objects.filter(fk_rol__nombre_rol=ADMIN, estado=True).count()
                        if active_admin_count <= 1:
                            return Response(
                                {"detail": "No se puede cambiar el rol del único administrador activo."},
                                status=status.HTTP_400_BAD_REQUEST,
                            )

                serializer = AdminUserUpdateSerializer(usuario, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                updated = serializer.save()
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        _log(request.user, f"ActualizaciÃ³n de usuario: {updated.correo} por admin {admin_usuario.correo}", request)

        return _ok(
            data=AdminUserSerializer(updated).data,
            message="Usuario actualizado exitosamente.",
        )

    @action(detail=True, methods=["patch"], url_path="toggle-estado")
    def toggle_estado(self, request, pk=None):
        """Activar o desactivar un usuario.

        ValidaciÃ³n: un admin no puede desactivarse a sÃ­ mismo.
        """
        try:
            with transaction.atomic():
                usuario = Usuario.objects.select_related("fk_rol").select_for_update().get(pk=pk)

                admin_usuario = request.user.usuario
                if usuario.id_usuario == admin_usuario.id_usuario and usuario.estado:
                    return Response(
                        {"detail": "No puedes desactivar tu propia cuenta de administrador."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if usuario.estado and usuario.fk_rol and usuario.fk_rol.nombre_rol == ADMIN:
                    active_admin_count = Usuario.objects.filter(fk_rol__nombre_rol=ADMIN, estado=True).count()
                    if active_admin_count <= 1:
                        return Response(
                            {"detail": "No se puede desactivar al único administrador activo."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                usuario.estado = not usuario.estado
                usuario.save(update_fields=["estado"])
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        accion = "activado" if usuario.estado else "desactivado"
        _log(request.user, f"Usuario {accion}: {usuario.correo} por admin {admin_usuario.correo}", request)

        return _ok(
            data=AdminUserSerializer(usuario).data,
            message=f"Usuario {accion} exitosamente.",
        )
