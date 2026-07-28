"""Vistas para el módulo de Mermas (Waste)."""

import logging

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError

from rassa.models import DecisionMerma, Merma, ProductoSemanal
from rassa.permissions.role_permissions import ADMIN, VENDEDOR, HasRole
from rassa.views import CatalogPagination, _log
from rassa.views import _ok as ok_response

from .serializers import DecisionMermaSerializer, MermaCreateSerializer, MermaListSerializer

logger = logging.getLogger(__name__)


class DecisionMermaViewSet(viewsets.ModelViewSet):
    """ViewSet para el catálogo de decisiones de merma.

    Solo accesible por administradores. Las decisiones se listan activas
    por defecto (estado=True). Soft-delete al destruir.
    """

    queryset = DecisionMerma.objects.all()
    serializer_class = DecisionMermaSerializer
    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN)]
    pagination_class = CatalogPagination

    def get_queryset(self):
        qs = DecisionMerma.objects.all()
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "").lower() in ("true", "1")
        if not incluir_inactivos:
            qs = qs.filter(estado=True)
        return qs

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return ok_response(data=self.get_paginated_response(serializer.data).data)
        serializer = self.get_serializer(queryset, many=True)
        return ok_response(data=serializer.data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ok_response(data=serializer.data, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return ok_response(data=serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.estado = False
        instance.save(update_fields=["estado"])
        _log(self.request.user, f"DecisionMerma desactivada: {instance.decision} (id={instance.pk})", self.request)
        return ok_response(message="Decisión desactivada")


class MermaViewSet(viewsets.ViewSet):
    """ViewSet para registro y consulta de mermas.

    - List: accesible por Admin y Vendedor.
    - Create: accesible por Admin y Vendedor. Descuenta stock del
      ProductoSemanal dentro de una transacción atómica con lock.
    """

    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN, VENDEDOR)]
    pagination_class = CatalogPagination

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class()
        return self._paginator

    def get_queryset(self):
        return (
            Merma.objects.select_related(
                "fk_producto_semanal__fk_producto",
                "fk_producto_semanal__fk_publicacion",
                "fk_decision",
            )
            .all()
            .order_by("-creado_en")
        )

    def list(self, request):
        queryset = self.get_queryset()
        page = self.paginator.paginate_queryset(queryset, request)
        serializer = MermaListSerializer(page, many=True)
        return ok_response(data=self.paginator.get_paginated_response(serializer.data).data)

    def create(self, request):
        serializer = MermaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        producto_semanal_id = validated["fk_producto_semanal"].pk
        cantidad = validated["cantidad"]

        try:
            with transaction.atomic():
                try:
                    producto = (
                        ProductoSemanal.objects.select_for_update().get(pk=producto_semanal_id)
                    )
                except ProductoSemanal.DoesNotExist as err:
                    raise NotFound("El producto semanal especificado no existe.") from err

                if producto.stock < cantidad:
                    raise ValidationError(
                        {
                            "fk_producto_semanal": (
                                f"Stock insuficiente. Disponible: {producto.stock}, "
                                f"solicitado: {cantidad}."
                            )
                        }
                    )

                producto.stock -= cantidad
                producto.save(update_fields=["stock"])

                merma = Merma.objects.create(
                    fk_producto_semanal=producto,
                    cantidad=cantidad,
                    motivo=validated["motivo"],
                    comentarios=validated.get("comentarios", ""),
                    fk_decision=validated["fk_decision"],
                )

        except ValidationError:
            raise
        except NotFound:
            raise
        except Exception as exc:
            logger.error("Error inesperado al registrar merma: %s", exc)
            return ok_response(
                message="Error al registrar la merma. Intente de nuevo.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        _log(request.user, f"merma_creada Merma #{merma.id_merma} — {merma.motivo}", request)
        logger.info("Merma #%s registrada — producto_semanal=%s, cantidad=%s", merma.id_merma, producto_semanal_id, cantidad)

        output_serializer = MermaListSerializer(merma)
        return ok_response(
            data=output_serializer.data,
            message="Merma registrada",
            status_code=status.HTTP_201_CREATED,
        )
