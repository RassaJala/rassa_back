"""Vistas para el módulo de Liquidaciones."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, connection, transaction
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
    estado_entregado = EstadoPedido.objects.get(tipo_estado=ESTADO_PEDIDO_ENTREGADO)
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
            liquidaciones__isnull=True,
        )
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


def _ventas_snapshot(liquidacion: Liquidacion):
    """Retorna los registros LiquidacionVenta del snapshot de la liquidación."""
    return list(
        liquidacion.ventas.select_related("fk_pedido__fk_cliente__fk_persona")
        .prefetch_related("fk_pedido__pago_set")
        .order_by("id_liquidacion_venta")
    )


def _build_detalle_output(liquidacion: Liquidacion, ventas):
    """Serializa el detalle de una liquidación con sus ventas y pago.

    Centraliza la construcción de la respuesta que se repetía en 3 lugares
    (retrieve, calcular, marcar_pagada) — revisión 4R R2.
    """
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
    """Detecta deadlocks (40P01) o timeouts de lock (55P03) en PostgreSQL."""
    if connection.vendor != "postgresql":
        return False
    cause = exc.__cause__ or exc.__context__
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    return sqlstate in ("40P01", "55P03")


def _set_lock_timeout(timeout_str: str = "5s"):
    """Limita el tiempo de espera por locks en la transacción actual de PostgreSQL (SET LOCAL)."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{timeout_str}'")


def _deadlock_response(message: str = "Conflicto de concurrencia. Reintente."):
    """Construye una respuesta 409 Conflict con la cabecera Retry-After para errores transitorios de concurrencia."""
    response = _ok(
        message=message,
        status_code=status.HTTP_409_CONFLICT,
    )
    response["Retry-After"] = "5"
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

    def retrieve(self, request, *args, **kwargs):
        # Override OkResponseMixin.retrieve para evitar el doble fetch:
        # el super().retrieve() llama a get_object() y luego a
        # get_serializer() que internamente llama a get_serializer_context()
        # que volvía a llamar a get_object(). Ahora cacheamos la instancia
        # en _cached_instance y la reutilizamos.
        instance = self.get_object()
        self._cached_instance = instance
        serializer = self.get_serializer(instance)
        return _ok(data=serializer.data)

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
        tasa = COMISION_RASSA

        inicio, fin_exclusive = _rango_semana(anio, semana)
        fin = fin_exclusive - timedelta(days=1)

        existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
        if existing:
            return _liquidacion_duplicada_response(existing)

        try:
            ventas = list(_ventas_agricultor_en_rango(agricultor.id_usuario, inicio, fin_exclusive))
        except EstadoPedido.DoesNotExist:
            # El seed no ha creado el estado "entregado" — es un error
            # operacional, no del usuario (revisión 4R R4).
            logger.error("EstadoPedido 'entregado' no existe en la BD. Ejecutar seed_rassa_data.")
            return _ok(
                message="Error de configuración: estado 'entregado' no está en la BD. Contacta al administrador.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not ventas:
            return _ok(
                message="No hay ventas entregadas para este agricultor en el periodo.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # Cap el tiempo que un select_for_update puede esperar
                # un lock. Sin esto, un pedido bloqueado puede colgar
                # `calcular` indefinidamente (revisión 4R R4).
                _set_lock_timeout("5s")
                pedido_ids = [p.id_pedido for p in ventas]
                list(PedidoCabecera.objects.select_for_update().filter(id_pedido__in=pedido_ids).order_by("pk"))

                existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
                if existing:
                    return _liquidacion_duplicada_response(existing)

                montos_map = _map_montos_agricultor_pedidos(pedido_ids, agricultor.id_usuario)
                monto_ventas = sum((montos_map.get(pid, Decimal("0.00")) for pid in pedido_ids), Decimal("0.00"))
                comision = (monto_ventas * tasa).quantize(Decimal("0.01"))
                monto_liquidar = monto_ventas - comision

                try:
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
                except IntegrityError as exc:
                    existing = _buscar_liquidacion_existente(agricultor, inicio, fin)
                    if existing:
                        return _liquidacion_duplicada_response(existing)
                    raise exc

                # Snapshot de las ventas que aportaron a esta liquidación
                # (item 4 de la revisión 4R — ver review R3/R4).
                # bulk_create es 1 INSERT con N VALUES, no N INSERTs.
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
        ventas_snapshot = _ventas_snapshot(liquidacion)
        output = _build_detalle_output(liquidacion, ventas_snapshot)

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
                # Cap el tiempo que un select_for_update puede esperar
                # un lock. Sin esto, un pedido bloqueado puede colgar
                # `marcar_pagada` indefinidamente (revisión 4R R4).
                _set_lock_timeout("5s")

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

                if liquidacion.estado == ESTADO_PAGADA:
                    pago_existente = liquidacion.fk_pago_liquidacion
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
                    ventas = _ventas_snapshot(liquidacion)
                    output = _build_detalle_output(liquidacion, ventas)
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
