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

    queryset = Familia.objects.filter(estado=True)
    serializer_class = FamiliaSerializer
    permission_classes = [IsAuthenticated, HasRole("Admin")]

    def perform_destroy(self, instance):
        """Realiza un borrado lógico (soft-delete) de la familia."""
        with transaction.atomic():
            instance.estado = False
            instance.save()
            # Desactivar también los miembros de la familia
            FamiliaUsuario.objects.filter(fk_familia=instance).update(estado=False)
            _log(
                self.request.user,
                f"soft_delete familia id={instance.id_familia} nombre={instance.nombre_familia}",
                self.request,
            )

    @action(detail=True, methods=["post"], url_path="asignar-jefe")
    def asignar_jefe(self, request, pk=None):
        """Asigna o cambia el jefe de familia de un grupo familiar."""
        familia = self.get_object()
        jefe_id = request.data.get("fk_jefe_familia")

        if not jefe_id:
            raise ValidationError({"fk_jefe_familia": "El ID del jefe de familia es requerido."})

        try:
            nuevo_jefe = Usuario.objects.get(id_usuario=jefe_id, estado=True)
        except Usuario.DoesNotExist as err:
            raise ValidationError({"fk_jefe_familia": "El usuario especificado no existe o está inactivo."}) from err

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

    queryset = FamiliaUsuario.objects.filter(estado=True)
    serializer_class = FamiliaMiembroSerializer
    permission_classes = [IsAuthenticated, HasRole("Admin")]

    def perform_destroy(self, instance):
        """Realiza un borrado lógico de la asociación del miembro."""
        with transaction.atomic():
            familia = instance.fk_familia
            # Si el miembro a remover es el jefe, limpiar fk_jefe_familia
            if familia.fk_jefe_familia == instance.fk_usuario:
                familia.fk_jefe_familia = None
                familia.save()

            instance.estado = False
            instance.save()
            _log(
                self.request.user,
                f"remover_miembro usuario={instance.fk_usuario.correo} familia={familia.nombre_familia}",
                self.request,
            )
