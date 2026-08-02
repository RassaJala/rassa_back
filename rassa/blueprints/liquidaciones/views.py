"""Vistas para el módulo de Liquidaciones."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import DatabaseError, connection, transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from rassa.blueprints.liquidaciones.constants import (
    ESTADO_PAGADA,
    ESTADO_PENDIENTE,
    MSG_LIQUIDACION_DUPLICADA,
)
from rassa.models import (
    DetallePedido,
    EstadoPedido,
    Liquidacion,
    LiquidacionVenta,
    Pago,
    PedidoCabecera,
)
from rassa.permissions.role_permissions import ADMIN, AGRICULTOR, HasRole
from rassa.views import CatalogPagination, OkResponseMixin, _log, _ok

from .serializers import (
    CalcularLiquidacionSerializer,
    LiquidacionDetalleSerializer,
    LiquidacionListSerializer,
    MarcarPagadaSerializer,
)

logger = logging.getLogger(__name__)


def _rango_semana(year: int, week: int) -> tuple[date, date]:
    """Retorna (lunes_inclusive, lunes_siguiente_exclusive) en zona local."""
    lunes = date.fromisocalendar(year, week, 1)
    return lunes, lunes + timedelta(days=7)


def _ventas_agricultor_en_rango(agricultor_id: int, inicio: date, fin_exclusive: date):
    """Pedidos entregados con al menos un DetallePedido del agricultor en el rango.

    inicio es inclusivo, fin_exclusive es exclusivo. Los pedidos con
    `creado_en` en la fecha fin_exclusive (lunes siguiente) NO cuentan.
    """
    estado_entregado = EstadoPedido.objects.get(tipo_estado="entregado")
    pedido_ids = (
        DetallePedido.objects.filter(fk_producto_semanal__fk_publicacion__fk_agricultor_id=agricultor_id)
        .values_list("fk_pedido_id", flat=True)
        .distinct()
    )
    return (
        PedidoCabecera.objects.filter(
            id_pedido__in=pedido_ids,
            fk_estado=estado_entregado,
            creado_en__date__gte=inicio,
            creado_en__date__lt=fin_exclusive,
        )
        .select_related("fk_cliente__fk_persona")
        .prefetch_related("pago_set")
        .order_by("creado_en")
    )


def _ventas_snapshot(liquidacion: Liquidacion) -> list[PedidoCabecera]:
    """Retorna los pedidos del snapshot de la liquidación, en el orden del snapshot.

    Cierra el riesgo de inconsistencia entre `monto_ventas` y las ventas
    mostradas en el detalle (revisión 4R R3/R4 — ventas en vivo).
    """
    snapshot_ids = list(liquidacion.ventas.order_by("id_liquidacion_venta").values_list("fk_pedido_id", flat=True))
    if not snapshot_ids:
        return []
    pedidos = (
        PedidoCabecera.objects.filter(id_pedido__in=snapshot_ids)
        .select_related("fk_cliente__fk_persona")
        .prefetch_related("pago_set")
    )
    pedido_by_id = {p.id_pedido: p for p in pedidos}
    return [pedido_by_id[pid] for pid in snapshot_ids if pid in pedido_by_id]


def _build_detalle_output(liquidacion: Liquidacion, ventas):
    """Serializa el detalle de una liquidación con sus ventas y pago.

    Centraliza la construcción de la respuesta que se repetía en 3 lugares
    (retrieve, calcular, marcar_pagada) — revisión 4R R2.
    """
    liquidacion_full = _reload_liquidacion(liquidacion.pk)
    return LiquidacionDetalleSerializer(
        liquidacion_full,
        context={"ventas_queryset": ventas},
    ).data


def _reload_liquidacion(pk) -> Liquidacion:
    """Refetch a Liquidacion with its relations populated."""
    return Liquidacion.objects.select_related(
        "fk_agricultor__fk_persona",
        "fk_pago_liquidacion__fk_tipo",
    ).get(pk=pk)


def _buscar_liquidacion_existente(agricultor, inicio: date, fin: date) -> Liquidacion | None:
    """Busca cualquier liquidación existente para el mismo (agricultor, periodo).

    Cualquier estado (pendiente, parcial o pagada) cuenta como duplicado.
    Una liquidación `pagada` es terminal: no se puede re-calcular el mismo
    periodo. Esto cierra el hueco financiero de doble pago.
    """
    return (
        Liquidacion.objects.filter(
            fk_agricultor=agricultor,
            periodo_inicio=inicio,
            periodo_fin=fin,
        )
        .order_by("-creado_en")
        .first()
    )


def _liquidacion_duplicada_response(existing: Liquidacion):
    return _ok(
        message=MSG_LIQUIDACION_DUPLICADA.format(id=existing.id_liquidacion),
        data={"id_liquidacion_existente": existing.id_liquidacion},
        status_code=status.HTTP_409_CONFLICT,
    )


def _is_deadlock(exc: DatabaseError) -> bool:
    """Detecta deadlocks de PostgreSQL (psycopg2)."""
    if connection.vendor != "postgresql":
        return False
    cause = exc.__cause__ or exc.__context__
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    return sqlstate == "40P01"


class LiquidacionViewSet(
    OkResponseMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet para liquidaciones semanales por agricultor.

    Solo Admin puede consultar/operar. Las liquidaciones se calculan con
    ventas en estado 'entregado' y se pagan creando un Pago con fk_pedido=NULL
    enlazado por Liquidacion.fk_pago_liquidacion.
    """

    permission_classes = [IsAuthenticated, HasRole(ADMIN)]
    pagination_class = CatalogPagination
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        if self.action == "calcular":
            self.throttle_scope = "liquidaciones_calcular"
        elif self.action == "marcar_pagada":
            self.throttle_scope = "liquidaciones_pagada"
        else:
            self.throttle_scope = "liquidaciones_read"
        return super().get_throttles()

    def get_queryset(self):
        qs = Liquidacion.objects.select_related(
            "fk_agricultor__fk_persona",
            "fk_pago_liquidacion__fk_tipo",
        ).order_by("-creado_en")
        params = self.request.query_params
        try:
            agricultor = params.get("agricultor")
            if agricultor:
                # Validamos que sea int antes de pasar a .filter() para no
                # terminar en un 500 por ValueError al castear (revisión 4R R1).
                qs = qs.filter(fk_agricultor_id=int(agricultor))
            estado = params.get("estado")
            if estado:
                qs = qs.filter(estado=estado)
            periodo_inicio = params.get("periodo_inicio")
            if periodo_inicio:
                qs = qs.filter(periodo_inicio__gte=date.fromisoformat(periodo_inicio))
            periodo_fin = params.get("periodo_fin")
            if periodo_fin:
                qs = qs.filter(periodo_fin__lte=date.fromisoformat(periodo_fin))
        except (ValueError, TypeError) as exc:
            # Parámetro mal formado: ?agricultor=abc o ?periodo_inicio=basura.
            raise ValidationError(f"Parámetro de búsqueda inválido: {exc}") from exc
        return qs

    def get_serializer_class(self):
        if self.action == "calcular":
            return CalcularLiquidacionSerializer
        if self.action == "marcar_pagada":
            return MarcarPagadaSerializer
        if self.action == "retrieve":
            return LiquidacionDetalleSerializer
        return LiquidacionListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.action == "retrieve":
            instance = self.get_object()
            ctx["ventas_queryset"] = _ventas_snapshot(instance)
        return ctx

    @action(detail=False, methods=["post"], url_path="calcular")
    def calcular(self, request):
        serializer = CalcularLiquidacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agricultor = serializer.context["agricultor_obj"]
        # Defensa en profundidad: el serializer ya valida, pero re-aseguramos
        # el rol y el estado en caso de que el serializer sea reusado sin context.
        if agricultor.fk_rol.nombre_rol != AGRICULTOR or not agricultor.estado:
            return _ok(
                message="El usuario no es un agricultor activo.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        semana = serializer.validated_data["semana"]
        anio = serializer.validated_data["anio"]
        tasa = serializer.validated_data["tasa_comision"]

        inicio, fin_exclusive = _rango_semana(anio, semana)
        fin = fin_exclusive - timedelta(days=1)

        existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
        if existing:
            return _liquidacion_duplicada_response(existing)

        ventas = list(_ventas_agricultor_en_rango(agricultor.id_usuario, inicio, fin_exclusive))
        if not ventas:
            return _ok(
                message="No hay ventas entregadas para este agricultor en el periodo.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                pedido_ids = [p.id_pedido for p in ventas]
                list(PedidoCabecera.objects.select_for_update().filter(id_pedido__in=pedido_ids).order_by("pk"))

                existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
                if existing:
                    return _liquidacion_duplicada_response(existing)

                monto_ventas = sum((p.total for p in ventas), Decimal("0.00"))
                comision = (monto_ventas * tasa).quantize(Decimal("0.01"))
                monto_liquidar = monto_ventas - comision

                liquidacion = Liquidacion.objects.create(
                    fk_agricultor=agricultor,
                    periodo_inicio=inicio,
                    periodo_fin=fin,
                    monto_ventas=monto_ventas,
                    comision=comision,
                    monto_liquidar=monto_liquidar,
                    estado=ESTADO_PENDIENTE,
                )

                # Snapshot de las ventas que aportaron a esta liquidación
                # (item 4 de la revisión 4R — ver review R3/R4).
                # bulk_create es 1 INSERT con N VALUES, no N INSERTs.
                LiquidacionVenta.objects.bulk_create(
                    [
                        LiquidacionVenta(
                            fk_liquidacion=liquidacion,
                            fk_pedido=p,
                            monto_aportado=p.total,
                        )
                        for p in ventas
                    ]
                )
        except DatabaseError as exc:
            if _is_deadlock(exc):
                logger.warning(
                    "Deadlock al calcular liquidación agricultor=%s semana=%s",
                    agricultor.id_usuario,
                    semana,
                )
                return _ok(
                    message="Conflicto de concurrencia al calcular. Reintente.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            raise

        liquidacion = _reload_liquidacion(liquidacion.pk)
        output = _build_detalle_output(liquidacion, ventas)

        _log(
            request.user,
            (
                f"calcular_liquidacion id={liquidacion.id_liquidacion} "
                f"agricultor={agricultor.id_usuario} ventas={len(ventas)} "
                f"monto_ventas={monto_ventas} comision={comision}"
            ),
            request,
        )
        logger.info(
            "Liquidación %s calculada para agricultor %s: %s ventas, $%s",
            liquidacion.id_liquidacion,
            agricultor.id_usuario,
            len(ventas),
            monto_ventas,
        )

        return _ok(
            data=output,
            message="Liquidación calculada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="marcar-pagada")
    def marcar_pagada(self, request, pk=None):
        serializer = MarcarPagadaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tipo_pago = serializer.validated_data["tipo_pago"]
        referencia = serializer.validated_data.get("referencia", "")

        try:
            with transaction.atomic():
                # Lock first (no select_related — PostgreSQL forbids
                # FOR UPDATE on the nullable side of an outer join).
                try:
                    locked_id = (
                        Liquidacion.objects.select_for_update()
                        .filter(pk=pk)
                        .values_list("id_liquidacion", flat=True)
                        .first()
                    )
                except DatabaseError as exc:
                    if _is_deadlock(exc):
                        logger.warning("Deadlock al marcar pagada liquidacion=%s", pk)
                        return _ok(
                            message="Conflicto de concurrencia. Reintente.",
                            status_code=status.HTTP_409_CONFLICT,
                        )
                    raise

                if locked_id is None:
                    return _ok(
                        message="Liquidación no encontrada.",
                        status_code=status.HTTP_404_NOT_FOUND,
                    )

                liquidacion = Liquidacion.objects.select_related("fk_agricultor__fk_persona").get(pk=pk)

                if liquidacion.estado == ESTADO_PAGADA:
                    return _ok(
                        message="La liquidación ya está marcada como pagada.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    pago = Pago.objects.create(
                        fk_pedido=None,
                        fk_tipo_id=tipo_pago,
                        monto=liquidacion.monto_liquidar,
                        referencia=referencia,
                    )
                except DatabaseError as exc:
                    if _is_deadlock(exc):
                        logger.warning("Deadlock al generar folio de pago liquidacion=%s", pk)
                        return _ok(
                            message="Conflicto de concurrencia al generar folio. Reintente.",
                            status_code=status.HTTP_409_CONFLICT,
                        )
                    logger.error("Error al registrar pago de liquidación %s: %s", pk, exc)
                    return _ok(
                        message="Error al procesar el pago de la liquidación. Intente de nuevo.",
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                liquidacion.fk_pago_liquidacion = pago
                liquidacion.estado = ESTADO_PAGADA
                liquidacion.save(update_fields=["fk_pago_liquidacion", "estado"])
        except DatabaseError as exc:
            if _is_deadlock(exc):
                logger.warning("Deadlock en marcar_pagada liquidacion=%s", pk)
                return _ok(
                    message="Conflicto de concurrencia. Reintente.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            raise

        liquidacion = _reload_liquidacion(liquidacion.pk)
        ventas = _ventas_snapshot(liquidacion)
        output = _build_detalle_output(liquidacion, ventas)

        _log(
            request.user,
            (f"marcar_pagada_liquidacion id={liquidacion.id_liquidacion} folio_pago={pago.folio} monto={pago.monto}"),
            request,
        )
        logger.info(
            "Liquidación %s marcada como pagada (folio %s, $%s)",
            liquidacion.id_liquidacion,
            pago.folio,
            pago.monto,
        )

        return _ok(
            data=output,
            message=f"Liquidación marcada como pagada. Folio: {pago.folio}.",
        )
