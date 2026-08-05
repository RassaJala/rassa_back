"""Vistas para el módulo de Mermas (Waste)."""

import logging

from django.db import transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from rest_framework import mixins, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from rassa.models import DecisionMerma, Merma, ProductoSemanal
from rassa.permissions.role_permissions import ADMIN, VENDEDOR, HasRole
from rassa.utils import parse_date_param
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
    create_message = "Decisión registrada correctamente."
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


class MermaViewSet(
    OkResponseMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    GenericViewSet,
):
    """ViewSet para registro y consulta de mermas.

    - List / Retrieve: accesible por Admin y Vendedor.
    - Create: accesible por Admin y Vendedor. Descuenta stock del
      ProductoSemanal dentro de una transacción atómica con lock.
    """

    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN, VENDEDOR)]
    pagination_class = CatalogPagination

    def get_serializer_class(self):
        if self.action == "create":
            return MermaCreateSerializer
        return MermaListSerializer

    def _parse_fk_pedido(self, raw) -> int | None:
        """Validate and return an integer fk_pedido or raise ValidationError."""
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as err:
            raise ValidationError({"fk_pedido": "fk_pedido debe ser un número entero válido."}) from err

    @staticmethod
    def _rol_nombre(usuario) -> str | None:
        """Return the user's role name, or None when unknown (null-safe)."""
        rol = getattr(usuario, "fk_rol", None) if usuario is not None else None
        return rol.nombre_rol if rol is not None else None

    def get_queryset(self):
        qs = Merma.objects.select_related(
            "fk_producto_semanal__fk_producto",
            "fk_producto_semanal__fk_publicacion",
            "fk_decision",
            "fk_pedido__fk_cliente__fk_persona",
            "fk_pedido__fk_vendedor__fk_persona",
            "fk_pedido__fk_estado",
        )
        # Un vendedor solo ve las mermas de sus propios pedidos; el admin las ve todas.
        usuario = getattr(self.request.user, "usuario", None)
        if self._rol_nombre(usuario) != ADMIN and usuario is not None:
            qs = qs.filter(fk_pedido__fk_vendedor_id=usuario.pk)
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "").lower() in ("true", "1")
        if not incluir_inactivos:
            qs = qs.filter(estado=True)
        fk_pedido = self._parse_fk_pedido(self.request.query_params.get("fk_pedido"))
        if fk_pedido is not None:
            qs = qs.filter(fk_pedido_id=fk_pedido)
        return qs.order_by("-creado_en")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        producto_semanal_id = validated["fk_producto_semanal"]
        cantidad = validated["cantidad"]
        pedido = validated["fk_pedido"]

        # Un vendedor solo puede registrar mermas de sus propios pedidos.
        # (El admin puede registrar mermas de cualquier pedido.)
        usuario = getattr(request.user, "usuario", None)
        if self._rol_nombre(usuario) != ADMIN and (usuario is None or pedido.fk_vendedor_id != usuario.pk):
            raise ValidationError({"fk_pedido": "El pedido no pertenece al vendedor autenticado."})

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
        except Exception:
            logger.exception("Error inesperado al registrar merma")
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


class MermaResumenView(APIView):
    """Resumen agregado de mermas agrupadas por período, producto y decisión.

    ``producto_mas_afectado`` se calcula globalmente (todos los períodos), no
    por cada agrupación temporal. Si se requiere por período, esta semántica
    debe revisarse.

    Query params:
        fecha_desde (str, opcional): Fecha inicio (YYYY-MM-DD).
        fecha_hasta (str, opcional): Fecha fin (YYYY-MM-DD).
        producto_id (int, opcional): ID de producto para filtrar.
        agrupar_por (str, opcional): ``semana`` | ``mes`` (default).

    Respuesta:
        .. code-block:: json

            {
              "ok": true,
              "data": {
                "agrupacion": "mes",
                "total_general": 100,
                "producto_mas_afectado": {
                  "nombre": "Manzana",
                  "total": 50
                },
                "detalle": [
                  {
                    "periodo": "2026-07-01T00:00:00-03:00",
                    "producto_nombre": "Manzana",
                    "producto_id": 1,
                    "decision_nombre": "Donar",
                    "decision_id": 1,
                    "total_cantidad": 25,
                    "total_mermas": 3
                  }
                ]
              }
            }
    """

    permission_classes = [permissions.IsAuthenticated, HasRole(ADMIN)]

    def _parse_producto_id(self, raw: str | None) -> int | None:
        """Validate and return an integer producto_id or raise ValidationError."""
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as err:
            raise ValidationError({"producto_id": "producto_id debe ser un número entero válido."}) from err

    def _parse_agrupar_por(self, raw: str) -> str:
        """Validate and return 'mes' or 'semana' or raise ValidationError."""
        if raw not in ("mes", "semana"):
            raise ValidationError({"agrupar_por": "agrupar_por debe ser 'mes' o 'semana'."})
        return raw

    def get(self, request):
        qs = Merma.objects.filter(estado=True).select_related(
            "fk_producto_semanal__fk_producto",
            "fk_decision",
        )

        # --- Validar y parsear query params ---
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")
        producto_id_raw = request.query_params.get("producto_id")
        agrupar_por_raw = request.query_params.get("agrupar_por")

        if fecha_desde is not None:
            fecha_desde = parse_date_param(fecha_desde, "fecha_desde")
            qs = qs.filter(creado_en__date__gte=fecha_desde)
        if fecha_hasta is not None:
            fecha_hasta = parse_date_param(fecha_hasta, "fecha_hasta")
            qs = qs.filter(creado_en__date__lte=fecha_hasta)

        if fecha_desde is not None and fecha_hasta is not None and fecha_desde > fecha_hasta:
            raise ValidationError({"fecha_desde": "fecha_desde no puede ser mayor a fecha_hasta."})

        producto_id = self._parse_producto_id(producto_id_raw)
        if producto_id is not None:
            qs = qs.filter(fk_producto_semanal__fk_producto_id=producto_id)

        agrupar_por = "mes"
        if agrupar_por_raw is not None:
            agrupar_por = self._parse_agrupar_por(agrupar_por_raw)

        # total_general from filtered, ungrouped data
        total_general = qs.aggregate(total=Sum("cantidad"))["total"] or 0

        # producto_mas_afectado — product-level aggregation
        prod_totals = (
            qs.values(
                producto_nombre=F("fk_producto_semanal__fk_producto__nombre_producto"),
            )
            .annotate(total=Sum("cantidad"))
            .order_by("-total", "producto_nombre")
        )
        producto_mas_afectado = None
        if prod_totals:
            top = prod_totals.first()
            producto_mas_afectado = {
                "nombre": top["producto_nombre"],
                "total": top["total"],
            }

        # Detail — grouped by period, product, decision (limited)
        trunc_fn = TruncMonth if agrupar_por == "mes" else TruncWeek
        agrupado = (
            qs.annotate(
                periodo=trunc_fn("creado_en"),
                producto_nombre=F("fk_producto_semanal__fk_producto__nombre_producto"),
                producto_id=F("fk_producto_semanal__fk_producto__id_producto"),
                decision_nombre=F("fk_decision__decision"),
                decision_id=F("fk_decision__id_decision"),
            )
            .values(
                "periodo",
                "producto_nombre",
                "producto_id",
                "decision_nombre",
                "decision_id",
            )
            .annotate(
                total_cantidad=Sum("cantidad"),
                total_mermas=Count("id_merma"),
            )
            .order_by("-periodo", "-total_cantidad")
        )
        detalle = list(agrupado[:100])

        # Logging de auditoría
        logger.info(
            "Resumen mermas | usuario=%s filtros={fecha_desde=%s, fecha_hasta=%s, "
            "producto_id=%s, agrupar_por=%s} total_general=%s",
            request.user.email,
            fecha_desde,
            fecha_hasta,
            producto_id,
            agrupar_por,
            total_general,
        )

        return ok_response(
            data={
                "agrupacion": agrupar_por,
                "total_general": total_general,
                "producto_mas_afectado": producto_mas_afectado,
                "detalle": detalle,
            },
            message="Resumen de mermas",
        )
