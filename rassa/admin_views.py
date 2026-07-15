from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from rassa.admin_serializers import AdminUserSerializer, AdminUserUpdateSerializer
from rassa.models import Usuario
from rassa.permissions.role_permissions import HasRole

ADMIN = "Admin"


class AdminUsuarioViewSet(viewsets.ViewSet):
    """Endpoints administrativos para gestionar usuarios.

    Solo accesible por usuarios con rol Admin.

    Acciones:
        list     GET    /api/admin/usuarios/          â€” Listar con filtros
        retrieve GET    /api/admin/usuarios/{id}/     â€” Detalle de usuario
        update   PATCH  /api/admin/usuarios/{id}/     â€” Editar datos
        toggle   PATCH  /api/admin/usuarios/{id}/toggle-estado/ â€” Activar/desactivar
    """

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(ADMIN)]

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

        serializer = AdminUserSerializer(queryset, many=True)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

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
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        """Editar datos de un usuario (telÃ©fono, nombre, rol, etc.)."""
        try:
            usuario = Usuario.objects.select_related("fk_persona").get(pk=pk)
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        admin_usuario = request.user.usuario
        if usuario.id_usuario == admin_usuario.id_usuario and "role" in request.data:
            return Response(
                {"detail": "No puedes cambiar tu propio rol de administrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminUserUpdateSerializer(usuario, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        return Response(
            {
                "message": "Usuario actualizado exitosamente.",
                "data": AdminUserSerializer(updated).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["patch"], url_path="toggle-estado")
    def toggle_estado(self, request, pk=None):
        """Activar o desactivar un usuario.

        ValidaciÃ³n: un admin no puede desactivarse a sÃ­ mismo.
        """
        try:
            usuario = Usuario.objects.get(pk=pk)
        except Usuario.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        admin_usuario = request.user.usuario
        if usuario.id_usuario == admin_usuario.id_usuario and usuario.estado:
            return Response(
                {"detail": "No puedes desactivar tu propia cuenta de administrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if usuario.estado and usuario.fk_rol.nombre_rol == ADMIN:
            admin_count = Usuario.objects.filter(
                fk_rol__nombre_rol=ADMIN, estado=True
            ).count()
            if admin_count <= 1:
                return Response(
                    {"detail": "No se puede desactivar al único administrador activo."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        usuario.estado = not usuario.estado
        usuario.save(update_fields=["estado"])

        accion = "activado" if usuario.estado else "desactivado"
        return Response(
            {
                "message": f"Usuario {accion} exitosamente.",
                "data": AdminUserSerializer(usuario).data,
            },
            status=status.HTTP_200_OK,
        )
