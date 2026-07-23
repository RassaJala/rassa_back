"""Vistas para el módulo de Familias."""

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from rassa.models import Familia, FamiliaUsuario, Usuario
from rassa.permissions.role_permissions import HasRole
from rassa.views import _log, ok_response

from .serializers import (
    FamiliaMiembroSerializer,
    FamiliaSerializer,
)


class FamiliaViewSet(viewsets.ModelViewSet):
    """ViewSet para la gestión de Familias (CRUD)."""

    serializer_class = FamiliaSerializer
    permission_classes = [IsAuthenticated, HasRole("Admin")]

    def get_queryset(self):
        if self.action == "trash":
            return Familia.objects.filter(estado=False).order_by("-creado_en")
        if self.action in ("restore", "permanent"):
            return Familia.objects.filter(estado=False)
        return Familia.objects.filter(estado=True)

    def perform_destroy(self, instance):
        """Realiza un borrado lógico (soft-delete) de la familia."""
        if not instance.estado:
            return
        with transaction.atomic():
            instance.estado = False
            instance.save(update_fields=["estado"])
            # Desactivar también los miembros de la familia
            FamiliaUsuario.objects.filter(fk_familia=instance).update(estado=False)
        _log(
            self.request.user,
            f"soft_delete familia id={instance.id_familia} nombre={instance.nombre_familia}",
            self.request,
        )

    @action(detail=False, methods=["get"], url_path="trash")
    def trash(self, request, *args, **kwargs):
        """Lista las familias desactivadas (papelera)."""
        return self.list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None, *args, **kwargs):
        """Restaura una familia desactivada. Requiere asignar un nuevo jefe."""
        familia = self.get_object()

        if familia.estado:
            raise ValidationError({"familia": "La familia ya está activa."})

        jefe_id = request.data.get("fk_jefe_familia")
        if not jefe_id:
            raise ValidationError({"fk_jefe_familia": "El ID del jefe de familia es requerido para restaurar."})

        try:
            jefe_id_int = int(jefe_id)
        except (ValueError, TypeError) as err:
            raise ValidationError({"fk_jefe_familia": "El ID del jefe de familia debe ser un número entero."}) from err

        with transaction.atomic():
            try:
                jefe = Usuario.objects.select_for_update().get(pk=jefe_id_int, estado=True)
            except Usuario.DoesNotExist as err:
                raise ValidationError(
                    {"fk_jefe_familia": "El usuario especificado no existe o está inactivo."}
                ) from err

            # Bloquear si ya es miembro activo de OTRA familia
            if FamiliaUsuario.objects.filter(fk_usuario=jefe, estado=True).exclude(fk_familia=familia).exists():
                raise ValidationError({"fk_jefe_familia": "El usuario ya pertenece a otra familia activa."})

            familia.estado = True
            familia.fk_jefe_familia = jefe
            familia.save(update_fields=["estado", "fk_jefe_familia"])

            # Reactivar si ya existe, o crear si nunca fue miembro
            FamiliaUsuario.objects.update_or_create(
                fk_usuario=jefe,
                fk_familia=familia,
                defaults={"estado": True},
            )

        _log(
            request.user,
            f"restaurar familia id={familia.id_familia} nombre={familia.nombre_familia} jefe={jefe.correo}",
            request,
        )

        serializer = self.get_serializer(familia)
        return ok_response(
            data=serializer.data,
            message="Familia restaurada correctamente.",
        )

    @action(detail=True, methods=["post"], url_path="permanent")
    def permanent(self, request, pk=None, *args, **kwargs):
        """Elimina permanentemente una familia y sus relaciones."""
        familia = self.get_object()
        model_name = type(familia).__name__
        nombre = familia.nombre_familia
        pk_val = familia.pk
        with transaction.atomic():
            # Eliminar físicamente a los miembros asociados primero para evitar errores de llave foránea
            FamiliaUsuario.objects.filter(fk_familia=familia).delete()
            # Eliminar la familia físicamente
            familia.delete()
        _log(
            request.user,
            f"{model_name} eliminado permanentemente: {nombre} (id={pk_val})",
            request,
        )
        return ok_response(message="Familia eliminada permanentemente.")

    @action(detail=True, methods=["post"], url_path="asignar-jefe")
    def asignar_jefe(self, request, pk=None):
        """Asigna o cambia el jefe de familia de un grupo familiar."""
        familia = self.get_object()
        jefe_id = request.data.get("fk_jefe_familia")

        if not jefe_id:
            raise ValidationError({"fk_jefe_familia": "El ID del jefe de familia es requerido."})

        try:
            jefe_id_int = int(jefe_id)
            nuevo_jefe = Usuario.objects.get(id_usuario=jefe_id_int, estado=True)
        except (ValueError, TypeError, Usuario.DoesNotExist) as err:
            raise ValidationError(
                {"fk_jefe_familia": "El usuario especificado no existe, está inactivo o tiene un formato incorrecto."}
            ) from err

        # Validar que el jefe pertenezca a la familia
        es_miembro = FamiliaUsuario.objects.filter(fk_usuario=nuevo_jefe, fk_familia=familia, estado=True).exists()

        if not es_miembro:
            raise ValidationError(
                {"fk_jefe_familia": "El jefe de familia debe ser un miembro activo de la familia primero."}
            )

        with transaction.atomic():
            familia.fk_jefe_familia = nuevo_jefe
            familia.save()
            _log(
                request.user,
                f"asignar_jefe familia={familia.nombre_familia} jefe={nuevo_jefe.correo}",
                request,
            )

        serializer = self.get_serializer(familia)
        return ok_response(
            data=serializer.data,
            message="Jefe de familia asignado correctamente.",
        )


class FamiliaMiembroViewSet(viewsets.ModelViewSet):
    """ViewSet para la administración de integrantes de familias."""

    serializer_class = FamiliaMiembroSerializer
    permission_classes = [IsAuthenticated, HasRole("Admin")]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        queryset = FamiliaUsuario.objects.filter(estado=True)
        familia_id = self.request.query_params.get("fk_familia")
        if familia_id is not None:
            try:
                familia_id_int = int(familia_id)
            except (ValueError, TypeError) as err:
                raise ValidationError({"fk_familia": "El parámetro 'fk_familia' debe ser un número entero."}) from err

            if not Familia.objects.filter(id_familia=familia_id_int, estado=True).exists():
                raise ValidationError({"fk_familia": "La familia especificada no existe o está inactiva."})

            queryset = queryset.filter(fk_familia_id=familia_id_int)
        return queryset

    def perform_destroy(self, instance):
        """Desactiva la membresía del miembro de la familia (soft-delete)."""
        if not instance.estado:
            return
        with transaction.atomic():
            familia = instance.fk_familia
            if familia.fk_jefe_familia == instance.fk_usuario:
                familia.fk_jefe_familia = None
                familia.save(update_fields=["fk_jefe_familia"])

            correo = instance.fk_usuario.correo
            nombre = familia.nombre_familia
            instance.estado = False
            instance.save(update_fields=["estado"])
        _log(
            self.request.user,
            f"remover_miembro usuario={correo} familia={nombre}",
            self.request,
        )
