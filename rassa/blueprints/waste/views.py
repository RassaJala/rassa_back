"""Vistas para el módulo de Mermas (Waste)."""

import logging

from django.db import transaction
from rest_framework import mixins, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from rassa.models import DecisionMerma, Merma, ProductoSemanal
from rassa.permissions.role_permissions import ADMIN, VENDEDOR, HasRole
from rassa.views import CatalogPagination, OkResponseMixin, _log
from rassa.views import _ok as ok_response

from .serializers import DecisionMermaSerializer, MermaCreateSerializer, MermaListSerializer

logger = logging.getLogger(__name__)


class DecisionMermaViewSet(OkResponseMixin, ModelViewSet):
    """ViewSet para el catálogo de decisiones de merma.

    Solo accesible por administradores. Las decisiones se listan activas
    por defecto (estado=True). Soft-delete al destruir.
    """

    queryset = DecisionMerma.objects.all()
    serializer_class = DecisionMermaSerializer
    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN)]
    pagination_class = CatalogPagination
    update_message = "Decisión actualizada correctamente."

    def get_queryset(self):
        qs = super().get_queryset()
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "").lower() in ("true", "1")
        if not incluir_inactivos:
            qs = qs.filter(estado=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.estado = False
        instance.save(update_fields=["estado"])
        _log(self.request.user, f"DecisionMerma desactivada: {instance.decision} (id={instance.pk})", self.request)
        return ok_response(message="Decisión desactivada")


class MermaViewSet(OkResponseMixin, mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet):
    """ViewSet para registro y consulta de mermas.

    - List: accesible por Admin y Vendedor.
    - Create: accesible por Admin y Vendedor. Descuenta stock del
      ProductoSemanal dentro de una transacción atómica con lock.
    """

    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN, VENDEDOR)]
    pagination_class = CatalogPagination

    def get_serializer_class(self):
        if self.action == "create":
            return MermaCreateSerializer
        return MermaListSerializer

    def get_queryset(self):
        qs = Merma.objects.select_related(
            "fk_producto_semanal__fk_producto",
            "fk_producto_semanal__fk_publicacion",
            "fk_decision",
        )
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "").lower() in ("true", "1")
        if not incluir_inactivos:
            qs = qs.filter(estado=True)
        return qs.order_by("-creado_en")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        producto_semanal_id = validated["fk_producto_semanal"]
        cantidad = validated["cantidad"]

        try:
            with transaction.atomic():
                producto_semanal = ProductoSemanal.objects.select_for_update().get(pk=producto_semanal_id)

                if producto_semanal.stock < cantidad:
                    raise ValidationError(
                        {
                            "fk_producto_semanal": (
                                f"Stock insuficiente. Disponible: {producto_semanal.stock}, solicitado: {cantidad}."
                            )
                        }
                    )

                producto_semanal.stock -= cantidad
                producto_semanal.save(update_fields=["stock"])

                merma = serializer.save(fk_producto_semanal=producto_semanal)

        except ValidationError:
            raise
        except ProductoSemanal.DoesNotExist:
            raise NotFound({"fk_producto_semanal": "El producto semanal no existe."}) from None
        except Exception as exc:
            logger.error("Error inesperado al registrar merma: %s", exc)
            return Response(
                {"ok": False, "message": "Error al registrar la merma. Intente de nuevo."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        _log(request.user, f"merma_creada Merma #{merma.id_merma} — {merma.motivo}", request)
        logger.info(
            "Merma #%s registrada — producto_semanal=%s, cantidad=%s",
            merma.id_merma,
            producto_semanal_id,
            cantidad,
        )

        output_serializer = MermaListSerializer(merma)
        return ok_response(
            data=output_serializer.data,
            message="Merma registrada",
            status_code=status.HTTP_201_CREATED,
        )
