"""Vistas para el módulo de Liquidaciones."""

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from rassa.blueprints.liquidaciones.constants import (
    COMISION_RASSA,
    ESTADO_PAGADA,
    ESTADO_PEDIDO_ENTREGADO,
    ESTADO_PENDIENTE,
    LOCK_TIMEOUT_SECONDS,
    MSG_LIQUIDACION_DUPLICADA,
    RETRY_AFTER_SECONDS,
)
from rassa.models import (
    DetallePedido,
    EstadoPedido,
    Liquidacion,
    LiquidacionVenta,
    Pago,
    PedidoCabecera,
    Usuario,
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
    """Retorna date objects (naive, representan fechas en la TZ configurada del proyecto).

    Las fechas representan días en la zona horaria configurada del proyecto
    (TIME_ZONE en settings). El filtro ``creado_en__date__gte/lt`` de Django
    convierte automáticamente el datetime UTC al TIME_ZONE antes de comparar.
    """
    lunes = date.fromisocalendar(year, week, 1)
    return lunes, lunes + timedelta(days=7)


def _ventas_agricultor_en_rango(agricultor_id: int, inicio: date, fin_exclusive: date):
    """Pedidos entregados con al menos un DetallePedido del agricultor en el rango.

    inicio es inclusivo, fin_exclusive es exclusivo. Los pedidos con
    `creado_en` en la fecha fin_exclusive (lunes siguiente) NO cuentan.
    """
    from django.db.models import Exists, OuterRef

    from rassa.models import LiquidacionVenta

    estado_entregado = EstadoPedido.objects.get(tipo_estado=ESTADO_PEDIDO_ENTREGADO)
    pedido_ids = (
        DetallePedido.objects.filter(fk_producto_semanal__fk_publicacion__fk_agricultor_id=agricultor_id)
        .values_list("fk_pedido_id", flat=True)
        .distinct()
    )

    # C1 Fix: Excluir pedidos solo si ya fueron liquidados para ESTE agricultor específico
    ya_liquidado_para_este_agricultor = LiquidacionVenta.objects.filter(
        fk_pedido=OuterRef("pk"),
        fk_liquidacion__fk_agricultor_id=agricultor_id,
    )

    return (
        PedidoCabecera.objects.filter(
            id_pedido__in=pedido_ids,
            fk_estado=estado_entregado,
            creado_en__date__gte=inicio,
            creado_en__date__lt=fin_exclusive,
        )
        .annotate(ya_liquidado=Exists(ya_liquidado_para_este_agricultor))
        .filter(ya_liquidado=False)
        .select_related("fk_cliente__fk_persona")
        .prefetch_related("pago_set")
        .order_by("creado_en")
    )


def _map_montos_agricultor_pedidos(pedido_ids: list[int], agricultor_id: int) -> dict[int, Decimal]:
    """Retorna un diccionario de pedido_id -> monto sumado de las líneas del agricultor."""
    from django.db.models import Sum

    lineas = (
        DetallePedido.objects.filter(
            fk_pedido_id__in=pedido_ids, fk_producto_semanal__fk_publicacion__fk_agricultor_id=agricultor_id
        )
        .values("fk_pedido_id")
        .annotate(total_agricultor=Sum("importe"))
    )
    return {item["fk_pedido_id"]: Decimal(str(item["total_agricultor"] or "0.00")) for item in lineas}


def _calcular_montos(ventas: list[PedidoCabecera], agricultor_id: int, tasa: Decimal):
    """Calcula monto_ventas, comision y monto_liquidar basándose en las líneas del agricultor."""
    pedido_ids = [p.id_pedido for p in ventas]
    montos_map = _map_montos_agricultor_pedidos(pedido_ids, agricultor_id)
    monto_ventas = sum((montos_map.get(pid, Decimal("0.00")) for pid in pedido_ids), Decimal("0.00"))
    comision = (monto_ventas * tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    monto_liquidar = monto_ventas - comision
    return montos_map, monto_ventas, comision, monto_liquidar


def _crear_liquidacion_con_snapshot(
    agricultor: Usuario,
    inicio: date,
    fin: date,
    monto_ventas: Decimal,
    tasa: Decimal,
    comision: Decimal,
    monto_liquidar: Decimal,
    ventas: list[PedidoCabecera],
    montos_map: dict[int, Decimal],
) -> Liquidacion:
    """Crea la liquidación y el snapshot en LiquidacionVenta en la misma transacción atómica (B1 Fix)."""
    with transaction.atomic():
        liquidacion = Liquidacion.objects.create(
            fk_agricultor=agricultor,
            periodo_inicio=inicio,
            periodo_fin=fin,
            monto_ventas=monto_ventas,
            tasa_comision=tasa,
            comision=comision,
            monto_liquidar=monto_liquidar,
            estado=ESTADO_PENDIENTE,
        )
        LiquidacionVenta.objects.bulk_create(
            [
                LiquidacionVenta(
                    fk_liquidacion=liquidacion,
                    fk_pedido=p,
                    monto_aportado=montos_map.get(p.id_pedido, Decimal("0.00")),
                )
                for p in ventas
            ]
        )
    return liquidacion


def _ventas_snapshot(liquidacion: Liquidacion):
    """Retorna los registros LiquidacionVenta del snapshot de la liquidación."""
    return list(
        liquidacion.ventas.select_related("fk_pedido__fk_cliente__fk_persona")
        .prefetch_related("fk_pedido__pago_set")
        .order_by("id_liquidacion_venta")
    )


def _build_detalle_output(liquidacion: Liquidacion, ventas=None):
    """Serializa el detalle de una liquidación con sus ventas y pago.

    Si no se pasa `ventas`, consulta automáticamente `_ventas_snapshot(liquidacion)`.
    """
    if ventas is None:
        ventas = _ventas_snapshot(liquidacion)
    return LiquidacionDetalleSerializer(
        liquidacion,
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


def _is_transient_error(exc: DatabaseError) -> bool:
    """Detecta deadlocks (40P01), timeouts de lock (55P03), cierres de transacción y cancelaciones (C6 Fix)."""
    if connection.vendor != "postgresql":
        return False
    cause = exc.__cause__ or exc.__context__
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    return sqlstate in ("40P01", "55P03", "57014", "08006", "57P01", "40001")


def _set_lock_timeout(timeout_str: str = LOCK_TIMEOUT_SECONDS):
    """Limita el tiempo de espera por locks en la transacción actual de PostgreSQL (SET LOCAL)."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{timeout_str}'")


def _deadlock_response(message: str = "Conflicto de concurrencia. Reintente."):
    """Construye una respuesta 409 Conflict con la cabecera Retry-After para errores transitorios de concurrencia."""
    logger.warning(
        "[METRIC_TRANSIENT_DB_ERROR] Conflicto de concurrencia o lock_timeout detectado. "
        "Emitiendo HTTP 409 con Retry-After: %s",
        RETRY_AFTER_SECONDS,
    )
    response = _ok(
        message=message,
        status_code=status.HTTP_409_CONFLICT,
    )
    response["Retry-After"] = str(RETRY_AFTER_SECONDS)
    return response


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
            self.throttle_scope = "liquidaciones_marcar_pagada"
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
            # _cached_instance se setea en retrieve() (override abajo)
            # para evitar un segundo SELECT a la BD (revisión 4R R2
            # SUGGESTION — doble fetch en retrieve).
            instance = getattr(self, "_cached_instance", None) or self.get_object()
            self._cached_instance = instance
            ctx["ventas_queryset"] = _ventas_snapshot(instance)
        return ctx

    def retrieve(self, request, pk=None, *args, **kwargs):
        try:
            int(pk)
        except (ValueError, TypeError):
            return _ok(
                message="ID de liquidación inválido.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            instance = self.get_object()
        except (Http404, Liquidacion.DoesNotExist):
            return _ok(
                message="Liquidación no encontrada.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        self._cached_instance = instance
        serializer = self.get_serializer(instance)
        return _ok(data=serializer.data)

    @action(detail=False, methods=["post"], url_path="calcular")
    def calcular(self, request):
        serializer = CalcularLiquidacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agricultor = serializer.context["agricultor_obj"]
        # Defensa en profundidad (revisión 4R R2): CalcularLiquidacionSerializer ya
        # valida el rol de AGRICULTOR y el campo `estado=True` en `validate_agricultor()`.
        # Se conserva esta verificación secundaria en la vista como salvaguarda ante
        # invocaciones directas o reutilizaciones del método sin pasar por la validación del serializador.
        if agricultor.fk_rol.nombre_rol != AGRICULTOR or not agricultor.estado:
            return _ok(
                message="El usuario no es un agricultor activo.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        semana = serializer.validated_data["semana"]
        anio = serializer.validated_data["anio"]
        tasa = COMISION_RASSA

        inicio, fin_exclusive = _rango_semana(anio, semana)
        fin = fin_exclusive - timedelta(days=1)

        # Pre-check de anti-duplicado fuera del lock
        existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
        if existing:
            return _liquidacion_duplicada_response(existing)

        liquidacion = None
        ventas_count = 0
        monto_ventas_total = Decimal("0.00")
        comision_total = Decimal("0.00")

        try:
            with transaction.atomic():
                _set_lock_timeout(LOCK_TIMEOUT_SECONDS)
                try:
                    ventas_iniciales = list(_ventas_agricultor_en_rango(agricultor.id_usuario, inicio, fin_exclusive))
                except EstadoPedido.DoesNotExist:
                    logger.error("EstadoPedido 'entregado' no existe en la BD. Ejecutar seed_rassa_data.")
                    return _ok(
                        message=(
                            "Error de configuración: estado 'entregado' no está en la BD. Contacta al administrador."
                        ),
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                if not ventas_iniciales:
                    return _ok(
                        message="No hay ventas entregadas para este agricultor en el periodo.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

                # Bloquear PedidoCabecera y DetallePedido sin outer joins (C3 Fix)
                pedido_ids = [p.id_pedido for p in ventas_iniciales]
                pedidos_lockeados = list(
                    PedidoCabecera.objects.select_for_update().filter(id_pedido__in=pedido_ids).order_by("pk")
                )
                list(
                    DetallePedido.objects.select_for_update().filter(
                        fk_pedido_id__in=pedido_ids,
                        fk_producto_semanal__fk_publicacion__fk_agricultor_id=agricultor.id_usuario,
                    )
                )

                # Re-validación atómica bulk sin N+1 queries
                ya_liquidados_set = set(
                    LiquidacionVenta.objects.filter(
                        fk_pedido_id__in=pedido_ids,
                        fk_liquidacion__fk_agricultor_id=agricultor.id_usuario,
                    ).values_list("fk_pedido_id", flat=True)
                )

                ventas = [
                    p
                    for p in pedidos_lockeados
                    if p.id_pedido not in ya_liquidados_set and p.fk_estado.tipo_estado == ESTADO_PEDIDO_ENTREGADO
                ]
                if not ventas:
                    return _ok(
                        message="No hay ventas entregadas para este agricultor en el periodo.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

                montos_map, monto_ventas_total, comision_total, monto_liquidar = _calcular_montos(
                    ventas, agricultor.id_usuario, tasa
                )

                liquidacion = _crear_liquidacion_con_snapshot(
                    agricultor,
                    inicio,
                    fin,
                    monto_ventas_total,
                    tasa,
                    comision_total,
                    monto_liquidar,
                    ventas,
                    montos_map,
                )
                ventas_count = len(ventas)
        except IntegrityError:
            existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
            if existing:
                return _liquidacion_duplicada_response(existing)
            raise
        except DatabaseError as exc:
            if _is_transient_error(exc):
                logger.warning(
                    "Error transitorio (deadlock/timeout) al calcular liquidación agricultor=%s semana=%s",
                    agricultor.id_usuario,
                    semana,
                )
                return _deadlock_response("Conflicto de concurrencia al calcular. Reintente.")
            raise

        liquidacion = _reload_liquidacion(liquidacion.pk)
        output = _build_detalle_output(liquidacion)

        _log(
            request.user,
            (
                f"calcular_liquidacion id={liquidacion.id_liquidacion} "
                f"agricultor={agricultor.id_usuario} ventas={ventas_count} "
                f"monto_ventas={monto_ventas_total} comision={comision_total}"
            ),
            request,
        )
        logger.info(
            "Liquidación %s calculada para agricultor %s: %s ventas, $%s",
            liquidacion.id_liquidacion,
            agricultor.id_usuario,
            ventas_count,
            monto_ventas_total,
        )

        return _ok(
            data=output,
            message="Liquidación calculada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="marcar-pagada")
    def marcar_pagada(self, request, pk=None):
        try:
            int(pk)
        except (ValueError, TypeError):
            return _ok(
                message="ID de liquidación inválido.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MarcarPagadaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tipo_pago = serializer.validated_data["tipo_pago"]
        referencia = serializer.validated_data.get("referencia", "")

        try:
            with transaction.atomic():
                # Contrato de Bloqueos (revisión 4R R4):
                # `marcar_pagada` bloquea la fila de `Liquidacion` para serializar pagos concurrentes.
                # `calcular` bloquea filas de `PedidoCabecera` para serializar cálculos.
                # La garantía incondicional anti-duplicados a nivel de periodo está asegurada por el
                # UniqueConstraint(fk_agricultor, periodo_inicio, periodo_fin) de la migración 0022.
                _set_lock_timeout(LOCK_TIMEOUT_SECONDS)

                locked_id = (
                    Liquidacion.objects.select_for_update()
                    .filter(pk=pk)
                    .values_list("id_liquidacion", flat=True)
                    .first()
                )

                if locked_id is None:
                    return _ok(
                        message="Liquidación no encontrada.",
                        status_code=status.HTTP_404_NOT_FOUND,
                    )

                liquidacion = _reload_liquidacion(pk)

                pago_existente = liquidacion.fk_pago_liquidacion

                # C8 Fix: Manejo robusto de inconsistencias de datos (Caso 1 y Caso 2)
                if liquidacion.estado == ESTADO_PENDIENTE and pago_existente is not None:
                    logger.warning(
                        "[DATA_INCONSISTENCY_WARNING] Liquidación %s tenía estado PENDIENTE pero "
                        "fk_pago_liquidacion=%s asignado. Auto-corrigiendo estado a PAGADA.",
                        pk,
                        pago_existente.pk,
                    )
                    liquidacion.estado = ESTADO_PAGADA
                    liquidacion.save(update_fields=["estado"])

                if liquidacion.estado == ESTADO_PAGADA and pago_existente is None:
                    logger.error(
                        "[DATA_INCONSISTENCY_ERROR] Liquidación %s tiene estado PAGADA pero "
                        "fk_pago_liquidacion es NULL.",
                        pk,
                    )
                    return _ok(
                        message="Inconsistencia de datos: la liquidación no tiene registro de pago.",
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                if liquidacion.estado == ESTADO_PAGADA or pago_existente is not None:
                    if pago_existente:
                        if pago_existente.fk_tipo_id != tipo_pago or (pago_existente.referencia or "") != referencia:
                            return _ok(
                                message=(
                                    f"La liquidación ya fue pagada previamente con datos distintos "
                                    f"(Folio: {pago_existente.folio}). No se puede modificar el pago."
                                ),
                                status_code=status.HTTP_409_CONFLICT,
                            )

                    # Idempotencia: si se re-envía la misma petición, devolvemos el detalle con 200 OK.
                    output = _build_detalle_output(liquidacion)
                    folio = pago_existente.folio if pago_existente else None
                    return _ok(
                        data=output,
                        message=f"La liquidación ya está marcada como pagada. Folio: {folio}.",
                    )

                pago = Pago.objects.create(
                    fk_pedido=None,
                    fk_tipo_id=tipo_pago,
                    monto=liquidacion.monto_liquidar,
                    referencia=referencia,
                )

                liquidacion.fk_pago_liquidacion = pago
                liquidacion.estado = ESTADO_PAGADA
                liquidacion.save(update_fields=["fk_pago_liquidacion", "estado"])
        except DatabaseError as exc:
            if _is_transient_error(exc):
                logger.warning("Error transitorio (deadlock/timeout) en marcar_pagada liquidacion=%s", pk)
                return _deadlock_response()
            logger.error("Error al registrar pago de liquidación %s: %s", pk, exc)
            return _ok(
                message="Error al procesar el pago de la liquidación. Intente de nuevo.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        liquidacion = _reload_liquidacion(liquidacion.pk)
        output = _build_detalle_output(liquidacion)

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
