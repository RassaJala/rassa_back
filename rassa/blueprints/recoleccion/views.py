"""Vistas del módulo de Recolecciones."""

import logging
from collections.abc import Mapping

from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from rassa.models import HistorialEstadoRecoleccion, Recoleccion, Usuario
from rassa.permissions.role_permissions import ADMIN, AGRICULTOR, VENDEDOR, HasRole
from rassa.utils import parse_date_param
from rassa.views import CatalogPagination, OkResponseMixin, _log, ok_response

from .serializers import (
    MSG_AGRICULTOR_NO_EXISTE,
    MSG_AGRICULTOR_SIN_ROL,
    RecoleccionCambiarEstadoSerializer,
    RecoleccionSerializer,
)

logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = {estado for estado, _ in Recoleccion.ESTADO_CHOICES}
ESTADOS_VALIDOS_STR = ", ".join(c[0] for c in Recoleccion.ESTADO_CHOICES)


def _pk_entero_valido(raw):
    """True si raw es un entero válido para pk (0 < valor <= 2**31 - 1)."""
    if raw is None:
        return False
    texto = str(raw)
    # isascii() excluye dígitos Unicode (ej. '٥', '²'): isdigit() los acepta
    # pero int() lanza ValueError -> 500.
    if not texto.isascii() or not texto.isdigit():
        return False
    try:
        # int() también lanza ValueError para strings ASCII de >4300 dígitos
        # (sys.set_int_max_str_digits, Python 3.12) -> 500.
        return 0 < int(texto) <= 2**31 - 1
    except ValueError:
        return False


def _constraint_violada(exc):
    """Nombre del constraint violado en un IntegrityError, o None si no aplica.

    Cross-DB: psycopg2 expone el constraint en ``diag.constraint_name`` (no en
    ``exc.constraint``), por eso se recorre la cadena de ``__cause__``. En
    SQLite el ``IntegrityError`` envuelve ``sqlite3.IntegrityError`` sin nombre
    de constraint; se detecta el código UNIQUE (``SQLITE_CONSTRAINT_UNIQUE``).
    HEURÍSTICA: en create/partial_update el único write unique de este módulo es
    el constraint parcial de recolección, así que un UNIQUE sin nombre se asume
    como ese constraint. Válido SOLO mientras este módulo tenga un único
    constraint unique en ese path; si mañana se agrega otro (un campo único en
    HistorialEstadoRecoleccion, un log único, etc.), un UNIQUE de SQLite se
    enmascararía como "ya tiene una recolección" y hay que revisar esta función.
    """
    causa = getattr(exc, "__cause__", None) or exc
    diag = getattr(causa, "diag", None)
    if diag is not None:
        return getattr(diag, "constraint_name", None)
    nombre = getattr(causa, "constraint", None)
    if nombre:
        return nombre
    if getattr(causa, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE":
        return "uniq_recoleccion_activa_agricultor_fecha"
    return None


class RecoleccionViewSet(OkResponseMixin, viewsets.ModelViewSet):
    """ViewSet de recolecciones con filtros y transiciones de estado.

    Los errores de validación se devuelven como dicts crudos de DRF a propósito
    (patrón del resto del proyecto): no se aplica un EXCEPTION_HANDLER global.

    Decisión de negocio actual: el AGRICULTOR solo lee sus recolecciones;
    agendar/cancelar queda para Admin/Vendedor. Si el negocio requiere que el
    agricultor agende/cancele, revisar get_permissions.

    El borrado de un Usuario con recolecciones fallará con ProtectedError
    (fk_agricultor es on_delete=PROTECT). Si algún día existe un admin de
    usuarios, ese error debería traducirse a 409 Conflict.
    """

    serializer_class = RecoleccionSerializer
    pagination_class = CatalogPagination
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        # Lectura (list/retrieve) para cualquier autenticado (el AGRICULTOR ve sus
        # propias recolecciones, filtradas en get_queryset); el resto de acciones
        # solo para Admin/Vendedor.
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasRole(ADMIN, VENDEDOR)]

    def get_throttles(self):
        # Scopes separados de lectura y escritura para no compartir budget: el
        # calendario del agricultor (list/retrieve) es lectura frecuente; las
        # escrituras del vendedor usan su propio scope (ver settings).
        self.throttle_scope = "recolecciones_read" if self.action in ("list", "retrieve") else "recolecciones_write"
        return super().get_throttles()

    def _get_recoleccion(self, pk, for_update=False):
        # pk fuera de rango (ej. 99999999999999999999) o no numérico -> 404 en
        # lugar de un 500 por DataError en Postgres.
        if not _pk_entero_valido(pk):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."})
        queryset = Recoleccion.objects.select_related("fk_agricultor__fk_persona")
        if for_update:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(pk=pk)
        except (Recoleccion.DoesNotExist, ValueError):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."}) from None

    def _get_recoleccion_locked(self, pk):
        return self._get_recoleccion(pk, for_update=True)

    def get_object(self):
        if not _pk_entero_valido(self.kwargs.get("pk")):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."})
        try:
            return super().get_object()
        except (Recoleccion.DoesNotExist, ValueError):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."}) from None

    def get_queryset(self):
        """Retorna las recolecciones con filtros opcionales por query params."""
        queryset = Recoleccion.objects.select_related("fk_agricultor__fk_persona__fk_localidad__fk_municipio")
        params = self.request.query_params
        # Lectura restringida: solo Admin/Vendedor (dataset completo) y Agricultor (solo
        # sus recolecciones). Un autenticado sin perfil Usuario no puede leer nada:
        # 403 explícito (evita el 200 con lista vacía silencioso para un User huérfano).
        # Un rol legítimo sin permiso de lectura (Cliente) ve lista vacía a propósito.
        usuario = getattr(self.request.user, "usuario", None)
        if usuario is None:
            raise PermissionDenied({"detalle": "El usuario no tiene un perfil válido para consultar recolecciones."})
        if not (usuario.tiene_rol(ADMIN) or usuario.tiene_rol(AGRICULTOR) or usuario.tiene_rol(VENDEDOR)):
            return queryset.none()
        if usuario.tiene_rol(AGRICULTOR):
            queryset = queryset.filter(fk_agricultor=usuario)
            fk_param = params.get("fk_agricultor")
            if fk_param:
                # Precedencia: primero validar que sea entero (un valor fuera de
                # rango debe dar "entero válido", no el mensaje de propiedad) y
                # luego comparar por valor numérico ("007" == 7 es el propio).
                if not _pk_entero_valido(fk_param):
                    raise ValidationError(
                        {"fk_agricultor": "El parámetro 'fk_agricultor' debe ser un número entero válido."}
                    )
                if int(fk_param) != usuario.id_usuario:
                    raise ValidationError(
                        {"fk_agricultor": "Un agricultor solo puede consultar sus propias recolecciones."}
                    )
        return self._aplicar_filtros(queryset, params)

    def _aplicar_filtros(self, queryset, params):
        """Aplica los filtros por query params (estado, fk_agricultor, fecha, rango)."""
        estado = params.get("estado")
        fk_agricultor = params.get("fk_agricultor")
        fecha = params.get("fecha")
        fecha_desde = params.get("fecha_desde")
        fecha_hasta = params.get("fecha_hasta")
        if estado:
            if estado not in ESTADOS_VALIDOS:
                raise ValidationError({"estado": f"Estado inválido. Valores válidos: {ESTADOS_VALIDOS_STR}."})
            queryset = queryset.filter(estado=estado)
        if fk_agricultor:
            # Entero fuera de rango -> 400 (no 500 por DataError).
            if not _pk_entero_valido(fk_agricultor):
                raise ValidationError(
                    {"fk_agricultor": "El parámetro 'fk_agricultor' debe ser un número entero válido."}
                )
            queryset = queryset.filter(fk_agricultor_id=fk_agricultor)
        if fecha:
            fecha = parse_date_param(fecha, "fecha")
            queryset = queryset.filter(fecha_recoleccion=fecha)
        if fecha_desde:
            fecha_desde = parse_date_param(fecha_desde, "fecha_desde")
            queryset = queryset.filter(fecha_recoleccion__gte=fecha_desde)
        if fecha_hasta:
            fecha_hasta = parse_date_param(fecha_hasta, "fecha_hasta")
            queryset = queryset.filter(fecha_recoleccion__lte=fecha_hasta)
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise ValidationError({"fecha_desde": "fecha_desde no puede ser mayor a fecha_hasta."})
        # nulls_last explícito para el orden de horas. Ojo: es un emulado por
        # Django, no un NULLS LAST nativo; en MySQL F(...).asc(nulls_last=True)
        # lanzaría NotSupportedError. Hoy el proyecto corre Postgres/SQLite donde
        # funciona; si algún día se migra a MySQL, revisar este orden.
        return queryset.order_by("fecha_recoleccion", F("hora_inicio").asc(nulls_last=True))

    def create(self, request, *args, **kwargs):
        if not isinstance(request.data, Mapping):
            raise ValidationError({"detalle": "El body debe ser un objeto JSON."})
        if "estado" in request.data:
            raise ValidationError({"estado": "Use /estado/ o /cancelar/ para cambiar el estado."})
        # Un fk_agricultor fuera de rango en el body (ej. 99999999999999999999) no
        # debe llegar al get(pk=...): en Postgres lanza NumericValueOutOfRange
        # (DataError) que DRF no convierte -> 500. Mismo guard que para query
        # params, aplicado ANTES de que el serializer toque la BD.
        if "fk_agricultor" in request.data and not _pk_entero_valido(request.data.get("fk_agricultor")):
            raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agricultor = serializer.validated_data["fk_agricultor"]
        try:
            with transaction.atomic():
                # Capas que protegen la unicidad en create:
                # 1. Pre-check del serializer (UX, sin lock; redundante con la 2,
                #    pero devuelve el mensaje con la key fk_agricultor antes de la BD).
                # 2. Re-check bajo el lock del agricultor (evita TOCTOU entre el
                #    validate y el save en creaciones concurrentes del mismo par).
                # 3. UniqueConstraint parcial en BD (garantía final; IntegrityError
                #    -> 400 discriminado por constraint name en el except de abajo).
                try:
                    agricultor = Usuario.objects.select_related("fk_persona").select_for_update().get(pk=agricultor.pk)
                except Usuario.DoesNotExist:
                    raise NotFound({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE}) from None
                if not agricultor.estado:
                    raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE})
                if not agricultor.tiene_rol(AGRICULTOR):
                    raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_SIN_ROL})
                if (
                    Recoleccion.objects.filter(
                        fk_agricultor=agricultor, fecha_recoleccion=serializer.validated_data["fecha_recoleccion"]
                    )
                    .exclude(estado="cancelado")
                    .exists()
                ):
                    raise ValidationError(
                        {"fk_agricultor": "El agricultor ya tiene una recolección programada para esta fecha."}
                    )
                recoleccion = serializer.save()
                # Evitar N+1 en la respuesta: serializer.data re-serializa serializer.instance
                # (el objeto creado por save()), cuyo fk_agricultor es el pre-lock, sin
                # fk_persona cacheada. Reasignar la instancia bloqueada (que ya trae
                # fk_persona por select_related) hace que get_agricultor_nombre no dispare
                # un query extra.
                serializer.instance.fk_agricultor = agricultor
                HistorialEstadoRecoleccion.objects.create(
                    fk_recoleccion=recoleccion,
                    estado_anterior=None,
                    estado_nuevo=recoleccion.estado,
                    fk_cambiado_por=getattr(request.user, "usuario", None),
                )
        except ValidationError:
            raise
        except IntegrityError as exc:
            if _constraint_violada(exc) != "uniq_recoleccion_activa_agricultor_fecha":
                logger.exception("IntegrityError inesperado al guardar recolección:")
                raise
            logger.warning("Recolección duplicada (constraint uniq_recoleccion_activa_agricultor_fecha).")
            raise ValidationError(
                {"fk_agricultor": "El agricultor ya tiene una recolección programada para esta fecha."}
            ) from None
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
        if not isinstance(request.data, Mapping):
            raise ValidationError({"detalle": "El body debe ser un objeto JSON."})
        if "estado" in request.data:
            raise ValidationError({"estado": "Use /estado/ o /cancelar/ para cambiar el estado."})
        # Mismo guard de rango que en create: un fk_agricultor fuera de rango en
        # el body no debe llegar al get(pk=...) (DataError de Postgres -> 500).
        if "fk_agricultor" in request.data and not _pk_entero_valido(request.data.get("fk_agricultor")):
            raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE})
        # Capas que protegen la unicidad en partial_update:
        # 1. Pre-check del serializer (UX, sin lock del agricultor).
        # 2. UniqueConstraint parcial en BD (garantía final; IntegrityError -> 400
        #    discriminado por constraint name).
        # ORDEN FIJO DE LOCKS (usuario -> recolección): si el PATCH reasigna
        # agricultor, el lock del Usuario se adquiere ANTES que el lock de la
        # Recolección, el mismo orden que create (usuario primero, luego el INSERT
        # de la recolección). Dos writers concurrentes del mismo par
        # agricultor+fecha con orden invertido de locks (uno creando y otro
        # reasignando) podrían interbloquearse y terminar en 500.
        try:
            with transaction.atomic():
                # Lectura SIN lock solo para validar el serializer: la fila puede
                # cambiar antes del save; se re-chequea bajo el lock más abajo.
                recoleccion = self._get_recoleccion(self.kwargs.get("pk"))
                serializer = self.get_serializer(recoleccion, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                if "fk_agricultor" in serializer.validated_data:
                    # Re-validar el agricultor bajo el lock (mismo patrón que create):
                    # entre el validate del serializer y el save podría haberse
                    # desactivado o cambiado de rol. Mismos mensajes que create.
                    try:
                        agricultor_nuevo = (
                            Usuario.objects.select_related("fk_persona")
                            .select_for_update()
                            .get(pk=serializer.validated_data["fk_agricultor"].pk)
                        )
                    except Usuario.DoesNotExist:
                        raise NotFound({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE}) from None
                    if not agricultor_nuevo.estado:
                        raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_NO_EXISTE})
                    if not agricultor_nuevo.tiene_rol(AGRICULTOR):
                        raise ValidationError({"fk_agricultor": MSG_AGRICULTOR_SIN_ROL})
                    # Reemplazar la instancia pre-lock por la bloqueada: evita TOCTOU
                    # y cachea fk_persona (select_related) para no disparar N+1 al
                    # re-serializar la respuesta.
                    serializer.validated_data["fk_agricultor"] = agricultor_nuevo
                # Lock de la fila + re-check de estado bajo el lock: evita el TOCTOU
                # entre la lectura sin lock (arriba) y el save.
                recoleccion = self._get_recoleccion_locked(self.kwargs.get("pk"))
                if recoleccion.estado in ("en_ruta", "recolectado", "cancelado"):
                    raise ValidationError(
                        {"estado": f"No se puede editar una recolección en estado '{recoleccion.estado}'."}
                    )
                # La instancia bloqueada puede diferir de la leída (otro writer pudo
                # modificarla): reasignarla antes de guardar para que save() use la
                # fila correcta y su fk_persona cacheada (sin N+1 al re-serializar).
                serializer.instance = recoleccion
                serializer.save()
        except ValidationError:
            raise
        except IntegrityError as exc:
            if _constraint_violada(exc) != "uniq_recoleccion_activa_agricultor_fecha":
                logger.exception("IntegrityError inesperado al guardar recolección:")
                raise
            logger.warning("Recolección duplicada (constraint uniq_recoleccion_activa_agricultor_fecha).")
            raise ValidationError(
                {"fk_agricultor": "El agricultor ya tiene una recolección programada para esta fecha."}
            ) from None
        _log(request.user, f"editar_recoleccion id={recoleccion.pk}", request)
        return ok_response(data=serializer.data, message="Recolección actualizada correctamente.")

    @action(detail=True, methods=["post"], url_path="estado")
    def cambiar_estado(self, request, pk=None):
        """Cambia el estado de una recolección validando las transiciones permitidas.

        Contrato ESTRICTO: pedir el estado actual devuelve 400 ("ya está en ese
        estado"). A diferencia de /cancelar/ (idempotente, 200 si ya estaba
        cancelado), este endpoint es una máquina de estados explícita y rechaza
        cambios sin transición.
        """
        if not isinstance(request.data, Mapping):
            raise ValidationError({"estado": "El body debe ser un objeto JSON."})
        if set(request.data.keys()) - {"estado"}:
            raise ValidationError({"estado": "Solo se permite el campo 'estado'."})
        with transaction.atomic():
            recoleccion = self._get_recoleccion_locked(pk)
            serializer = RecoleccionCambiarEstadoSerializer(recoleccion, data=request.data)
            serializer.is_valid(raise_exception=True)
            estado_anterior = recoleccion.estado
            recoleccion.estado = serializer.validated_data["estado"]
            recoleccion.save(update_fields=["estado"])
            HistorialEstadoRecoleccion.objects.create(
                fk_recoleccion=recoleccion,
                estado_anterior=estado_anterior,
                estado_nuevo=serializer.validated_data["estado"],
                fk_cambiado_por=getattr(request.user, "usuario", None),
            )
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
        """Cancela una recolección que aún no haya sido recolectada.

        Contrato IDEMPOTENTE: cancelar una recolección ya cancelada devuelve 200
        (acción de negocio "asegurar cancelado"). A diferencia de /estado/, que es
        estricto (400 si ya está en el estado pedido).
        """
        with transaction.atomic():
            recoleccion = self._get_recoleccion_locked(pk)
            if recoleccion.estado == "cancelado":
                # Camino idempotente: no hay transición de estado, así que no se
                # crea HistorialEstadoRecoleccion (el historial solo registra
                # transiciones reales). Se audita igual para dejar rastro.
                _log(request.user, f"cancelar_recoleccion id={recoleccion.pk} (ya estaba cancelada)", request)
                return ok_response(
                    data=RecoleccionSerializer(recoleccion).data,
                    message="La recolección ya estaba cancelada.",
                )
            serializer = RecoleccionCambiarEstadoSerializer(recoleccion, data={"estado": "cancelado"})
            serializer.is_valid(raise_exception=True)
            estado_anterior = recoleccion.estado
            recoleccion.estado = "cancelado"
            recoleccion.save(update_fields=["estado"])
            HistorialEstadoRecoleccion.objects.create(
                fk_recoleccion=recoleccion,
                estado_anterior=estado_anterior,
                estado_nuevo="cancelado",
                fk_cambiado_por=getattr(request.user, "usuario", None),
            )
        _log(request.user, f"cancelar_recoleccion id={recoleccion.pk}", request)
        return ok_response(
            data=RecoleccionSerializer(recoleccion).data,
            message="Recolección cancelada correctamente.",
        )
