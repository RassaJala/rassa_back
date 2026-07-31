"""Vistas del módulo de Recolecciones."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from rassa.models import Recoleccion
from rassa.permissions.role_permissions import ADMIN, VENDEDOR, HasRole
from rassa.views import CatalogPagination, _log, ok_response

from .serializers import RecoleccionCambiarEstadoSerializer, RecoleccionSerializer


class RecoleccionViewSet(viewsets.ModelViewSet):
    """ViewSet de recolecciones con filtros y transiciones de estado."""

    serializer_class = RecoleccionSerializer
    pagination_class = CatalogPagination
    permission_classes = [IsAuthenticated, HasRole(ADMIN, VENDEDOR)]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        """Retorna las recolecciones con filtros opcionales por query params."""
        queryset = Recoleccion.objects.select_related("fk_agricultor__fk_persona__fk_localidad__fk_municipio")
        params = self.request.query_params
        estado = params.get("estado")
        fk_agricultor = params.get("fk_agricultor")
        fecha = params.get("fecha")
        fecha_desde = params.get("fecha_desde")
        fecha_hasta = params.get("fecha_hasta")
        if estado:
            queryset = queryset.filter(estado=estado)
        if fk_agricultor:
            if not fk_agricultor.isdigit():
                raise ValidationError({"fk_agricultor": "El parámetro 'fk_agricultor' debe ser un número entero."})
            queryset = queryset.filter(fk_agricultor_id=fk_agricultor)
        if fecha:
            queryset = queryset.filter(fecha_recoleccion=fecha)
        if fecha_desde:
            queryset = queryset.filter(fecha_recoleccion__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_recoleccion__lte=fecha_hasta)
        return queryset.order_by("fecha_recoleccion", "hora_inicio")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recoleccion = serializer.save()
        _log(
            request.user,
            f"crear_recoleccion agricultor={recoleccion.fk_agricultor_id} fecha={recoleccion.fecha_recoleccion}",
            request,
        )
        return ok_response(
            data=serializer.data,
            message="Recolección creada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        recoleccion = self.get_object()
        if recoleccion.estado in ("recolectado", "cancelado"):
            raise ValidationError({"estado": f"No se puede editar una recolección en estado '{recoleccion.estado}'."})
        serializer = self.get_serializer(recoleccion, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _log(request.user, f"editar_recoleccion id={recoleccion.pk}", request)
        return ok_response(data=serializer.data, message="Recolección actualizada correctamente.")

    @action(detail=True, methods=["post"], url_path="estado")
    def cambiar_estado(self, request, pk=None):
        """Cambia el estado de una recolección validando las transiciones permitidas."""
        recoleccion = self.get_object()
        serializer = RecoleccionCambiarEstadoSerializer(recoleccion, data=request.data)
        serializer.is_valid(raise_exception=True)
        recoleccion.estado = serializer.validated_data["estado"]
        recoleccion.save(update_fields=["estado"])
        _log(
            request.user,
            f"cambiar_estado_recoleccion id={recoleccion.pk} estado={recoleccion.estado}",
            request,
        )
        return ok_response(
            data=RecoleccionSerializer(recoleccion).data,
            message="Estado actualizado correctamente.",
        )

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """Cancela una recolección que aún no haya sido recolectada."""
        recoleccion = self.get_object()
        if recoleccion.estado == "cancelado":
            raise ValidationError({"estado": "La recolección ya está cancelada."})
        if recoleccion.estado == "recolectado":
            raise ValidationError({"estado": "No se puede cancelar una recolección ya recolectada."})
        recoleccion.estado = "cancelado"
        recoleccion.save(update_fields=["estado"])
        _log(request.user, f"cancelar_recoleccion id={recoleccion.pk}", request)
        return ok_response(
            data=RecoleccionSerializer(recoleccion).data,
            message="Recolección cancelada correctamente.",
        )
