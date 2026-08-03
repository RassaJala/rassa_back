import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from rassa.models import ProductoSemanal, PublicacionSemanal
from rassa.permissions.role_permissions import AGRICULTOR, HasRole
from rassa.views import CatalogPagination, _log
from rassa.views import _ok as ok_response

from .serializers import (
    ProductoSemanalSerializer,
    PublicacionCurrentSerializer,
    PublicacionSerializer,
)

logger = logging.getLogger(__name__)


def calcular_proximo_lunes():
    """Calcula el próximo lunes a partir de hoy y su número de semana.

    Si hoy es lunes, retorna el lunes siguiente (no hoy), así los agricultores
    tienen toda la semana para preparar la publicación antes del lunes de entrega.
    """
    hoy = timezone.localdate()
    dias_hasta_lunes = (7 - hoy.weekday()) % 7
    if dias_hasta_lunes == 0:
        dias_hasta_lunes = 7
    prox_lunes = hoy + timedelta(days=dias_hasta_lunes)
    return prox_lunes, prox_lunes.isocalendar()[1]


def _error_si_no_lunes(accion="editarse"):
    """Retorna un mensaje de error si hoy no es lunes, o None si lo es.

    Se usa para restringir la creación y edición de publicaciones y sus
    productos al día lunes.
    """
    if timezone.localdate().weekday() != 0:
        return f"Las publicaciones solo pueden {accion} los lunes."
    return None


class PublicacionViewSet(viewsets.ViewSet):
    pagination_class = CatalogPagination
    throttle_scope = "publicaciones"

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(AGRICULTOR)]

    def get_throttles(self):
        if self.action in ("publish", "close"):
            self.throttle_scope = "publicaciones_write"
        return [ScopedRateThrottle()]

    def get_queryset(self):
        return (
            PublicacionSemanal.objects.filter(fk_agricultor=self.request.user.usuario)
            .prefetch_related("productosemanal_set")
            .order_by("-creado_en")
        )

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def _get_publicacion(self, pk, request):
        try:
            return self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound("Publicación no encontrada.") from err

    def list(self, request):
        queryset = self.get_queryset()
        estado = request.query_params.get("estado")
        if estado:
            queryset = queryset.filter(estado=estado)

        page = self.paginator.paginate_queryset(queryset, request)
        serializer = PublicacionSerializer(page, many=True)
        return ok_response(data=self.paginator.get_paginated_response(serializer.data).data)

    def create(self, request):
        error = _error_si_no_lunes("crearse")
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        prox_lunes, semana = calcular_proximo_lunes()
        publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=request.user.usuario,
            fecha_publicacion=prox_lunes,
            semana=semana,
            estado=PublicacionSemanal.ESTADO_BORRADOR,
        )
        serializer = PublicacionSerializer(publicacion)
        return ok_response(
            data=serializer.data,
            message="Publicación creada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        publicacion = self._get_publicacion(pk, request)
        serializer = PublicacionSerializer(publicacion)
        return ok_response(data=serializer.data)

    def destroy(self, request, pk=None):
        publicacion = self._get_publicacion(pk, request)

        if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
            return Response(
                {"error": "Solo se puede eliminar una publicación en estado borrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        error = _error_si_no_lunes()
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)

        publicacion.estado = PublicacionSemanal.ESTADO_CANCELADO
        publicacion.save(update_fields=["estado"])
        _log(request.user, f"Publicación #{publicacion.pk} cancelada", request)
        return ok_response(message="Publicación eliminada correctamente.")

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        with transaction.atomic():
            try:
                publicacion = self.get_queryset().select_for_update().get(pk=pk)
            except PublicacionSemanal.DoesNotExist as err:
                raise NotFound("Publicación no encontrada.") from err

            if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
                return Response(
                    {"error": "Solo se puede publicar una publicación en estado borrador."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            items = publicacion.productosemanal_set.filter(estado=ProductoSemanal.ESTADO_ACTIVO)
            if not items.exists():
                return Response(
                    {"error": "No hay productos activos para publicar."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            errores = []
            for item in items:
                errores_item = {}
                if item.stock <= 0:
                    errores_item["stock"] = "El stock debe ser mayor a 0."
                if item.precio <= 0:
                    errores_item["precio"] = "El precio debe ser mayor a 0."
                if not item.fk_unidad_id:
                    errores_item["fk_unidad"] = "La unidad es requerida."
                if not item.foto or item.foto.strip() == "":
                    errores_item["foto"] = "La foto es requerida para publicar."
                if errores_item:
                    errores.append(
                        {
                            "id_producto_semanal": item.id_producto_semanal,
                            **errores_item,
                        }
                    )

            if errores:
                return Response({"productos": errores}, status=status.HTTP_400_BAD_REQUEST)

            publicacion.estado = PublicacionSemanal.ESTADO_PUBLICADO
            publicacion.save(update_fields=["estado"])

        _log(request.user, f"Publicación #{publicacion.pk} publicada", request)
        logger.info("Publicación %s publicada por agricultor %s", publicacion.pk, request.user.usuario.pk)
        serializer = PublicacionSerializer(publicacion)
        return ok_response(data=serializer.data, message="Publicación publicada correctamente.")

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        with transaction.atomic():
            try:
                publicacion = self.get_queryset().select_for_update().get(pk=pk)
            except PublicacionSemanal.DoesNotExist as err:
                raise NotFound("Publicación no encontrada.") from err

            if publicacion.estado != PublicacionSemanal.ESTADO_PUBLICADO:
                return Response(
                    {"error": "Solo se puede cerrar una publicación en estado publicado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publicacion.estado = PublicacionSemanal.ESTADO_CERRADO
            publicacion.save(update_fields=["estado"])

        _log(request.user, f"Publicación #{publicacion.pk} cerrada", request)
        logger.info("Publicación %s cerrada por agricultor %s", publicacion.pk, request.user.usuario.pk)
        serializer = PublicacionSerializer(publicacion)
        return ok_response(data=serializer.data, message="Publicación cerrada correctamente.")


class ProductoSemanalViewSet(viewsets.ViewSet):
    pagination_class = CatalogPagination
    throttle_scope = "publicaciones"

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(AGRICULTOR)]

    def get_throttles(self):
        return [ScopedRateThrottle()]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def _get_publicacion(self, pub_id, request):
        try:
            return PublicacionSemanal.objects.get(pk=pub_id, fk_agricultor=request.user.usuario)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound("Publicación no encontrada.") from err

    def list(self, request, pub_id=None):
        publicacion = self._get_publicacion(pub_id, request)
        items = publicacion.productosemanal_set.filter(estado=ProductoSemanal.ESTADO_ACTIVO)
        page = self.paginator.paginate_queryset(items, request)
        serializer = ProductoSemanalSerializer(page, many=True)
        return ok_response(data=self.paginator.get_paginated_response(serializer.data).data)

    def create(self, request, pub_id=None):
        publicacion = self._get_publicacion(pub_id, request)
        error = _error_si_no_lunes()
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)
        if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
            return Response(
                {"error": "Solo se pueden agregar productos a una publicación en estado borrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductoSemanalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(fk_publicacion=publicacion)
        return ok_response(
            data=serializer.data,
            message="Producto agregado correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pub_id=None, pk=None):
        publicacion = self._get_publicacion(pub_id, request)
        error = _error_si_no_lunes()
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)
        if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
            return Response(
                {"error": "Solo se pueden modificar productos en una publicación en estado borrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = publicacion.productosemanal_set.get(pk=pk)
        except ProductoSemanal.DoesNotExist as err:
            raise NotFound("Producto no encontrado.") from err

        serializer = ProductoSemanalSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok_response(data=serializer.data, message="Producto actualizado correctamente.")

    def destroy(self, request, pub_id=None, pk=None):
        publicacion = self._get_publicacion(pub_id, request)
        error = _error_si_no_lunes()
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)
        if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
            return Response(
                {"error": "Solo se pueden eliminar productos en una publicación en estado borrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = publicacion.productosemanal_set.get(pk=pk)
        except ProductoSemanal.DoesNotExist as err:
            raise NotFound("Producto no encontrado.") from err

        item.estado = ProductoSemanal.ESTADO_INACTIVO
        item.save(update_fields=["estado"])
        return ok_response(message="Producto eliminado correctamente.")

    def restore(self, request, pub_id=None, pk=None):
        publicacion = self._get_publicacion(pub_id, request)
        try:
            item = publicacion.productosemanal_set.get(pk=pk, estado=ProductoSemanal.ESTADO_INACTIVO)
        except ProductoSemanal.DoesNotExist as err:
            raise NotFound("Producto no encontrado en la papelera.") from err

        error = _error_si_no_lunes()
        if error:
            return Response({"error": error}, status=status.HTTP_403_FORBIDDEN)
        if publicacion.estado != PublicacionSemanal.ESTADO_BORRADOR:
            return Response(
                {"error": "Solo se pueden restaurar productos en una publicación en estado borrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.estado = ProductoSemanal.ESTADO_ACTIVO
        item.save(update_fields=["estado"])
        return ok_response(data=ProductoSemanalSerializer(item).data, message="Producto restaurado correctamente.")


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def publicaciones_current(request):
    """Retorna las publicaciones publicadas de la semana actual (público)."""
    hoy = timezone.localdate()
    lunes = hoy - timedelta(days=hoy.weekday())
    domingo = lunes + timedelta(days=6)

    queryset = (
        PublicacionSemanal.objects.filter(
            fecha_publicacion__gte=lunes,
            fecha_publicacion__lte=domingo,
            estado=PublicacionSemanal.ESTADO_PUBLICADO,
        )
        .select_related("fk_agricultor__fk_persona")
        .prefetch_related(
            Prefetch(
                "productosemanal_set",
                queryset=ProductoSemanal.objects.filter(estado=ProductoSemanal.ESTADO_ACTIVO),
            ),
        )[:100]
    )

    serializer = PublicacionCurrentSerializer(queryset, many=True)
    return ok_response(data=serializer.data)


publicaciones_current.throttle_scope = "publicaciones_current"
