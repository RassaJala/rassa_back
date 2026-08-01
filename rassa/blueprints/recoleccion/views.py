"""Vistas del módulo de Recolecciones."""

import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated

from rassa.models import HistorialEstadoRecoleccion, Recoleccion, Usuario
from rassa.permissions.role_permissions import ADMIN, AGRICULTOR, VENDEDOR, HasRole
from rassa.utils import parse_date_param
from rassa.views import CatalogPagination, OkResponseMixin, _log, ok_response

from .serializers import RecoleccionCambiarEstadoSerializer, RecoleccionSerializer

logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = {estado for estado, _ in Recoleccion.ESTADO_CHOICES}


def _pk_entero_valido(raw):
    """True si raw es un entero válido para pk (0 < valor <= 2**31 - 1)."""
    if raw is None or not str(raw).isdigit():
        return False
    return 0 < int(raw) <= 2**31 - 1


def _constraint_violada(exc):
    """Nombre del constraint violado en un IntegrityError, o None si no aplica.

    Django envuelve el error de psycopg2 (que expone el constraint en
    ``diag.constraint_name``, no en ``exc.constraint``), por eso se recorre la
    cadena de ``__cause__``.
    """
    causa = getattr(exc, "__cause__", None) or exc
    diag = getattr(causa, "diag", None)
    if diag is not None:
        return getattr(diag, "constraint_name", None)
    return getattr(causa, "constraint", None)


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
    throttle_scope = "recolecciones"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        # Lectura (list/retrieve) para cualquier autenticado (el AGRICULTOR ve sus
        # propias recolecciones, filtradas en get_queryset); el resto de acciones
        # solo para Admin/Vendedor.
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasRole(ADMIN, VENDEDOR)]

    def _get_recoleccion_locked(self, pk):
        # pk fuera de rango (ej. 99999999999999999999) o no numérico -> 404 en
        # lugar de un 500 por DataError en Postgres.
        if not _pk_entero_valido(pk):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."})
        try:
            return Recoleccion.objects.select_related("fk_agricultor__fk_persona").select_for_update().get(pk=pk)
        except (Recoleccion.DoesNotExist, ValueError):
            raise NotFound({"id_recoleccion": "Recolección no encontrada."}) from None

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
        # sus recolecciones). Un autenticado sin perfil Usuario o con otro rol no debe
        # ver el dataset completo: no ve nada.
        roles_lectura = (ADMIN, AGRICULTOR, VENDEDOR)
        usuario = getattr(self.request.user, "usuario", None)
        if usuario is None or usuario.fk_rol.nombre_rol not in roles_lectura:
            return queryset.none()
        if usuario.fk_rol.nombre_rol == AGRICULTOR:
            queryset = queryset.filter(fk_agricultor=usuario)
            if params.get("fk_agricultor") and str(usuario.id_usuario) != params.get("fk_agricultor"):
                raise ValidationError(
                    {"fk_agricultor": "Un agricultor solo puede consultar sus propias recolecciones."}
                )
        estado = params.get("estado")
        fk_agricultor = params.get("fk_agricultor")
        fecha = params.get("fecha")
        fecha_desde = params.get("fecha_desde")
        fecha_hasta = params.get("fecha_hasta")
        if estado:
            if estado not in ESTADOS_VALIDOS:
                raise ValidationError(
                    {
                        "estado": (
                            f"Estado inválido. Valores válidos: {', '.join(c[0] for c in Recoleccion.ESTADO_CHOICES)}."
                        )
                    }
                )
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
            raise ValidationError("fecha_desde no puede ser mayor a fecha_hasta.")
        # nulls_last explícito: Postgres ordena NULLs last en ASC, pero MySQL los
        # pone primero; fijar el orden para que el comportamiento sea consistente.
        return queryset.order_by("fecha_recoleccion", F("hora_inicio").asc(nulls_last=True))

    def create(self, request, *args, **kwargs):
        if "estado" in request.data:
            raise ValidationError({"estado": "Use /estado/ o /cancelar/ para cambiar el estado."})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agricultor = serializer.validated_data["fk_agricultor"]
        try:
            with transaction.atomic():
                # Capa 1: el serializer ya validó el agricultor (capa UX).
                # El lock sobre el agricultor serializa recolecciones concurrentes del mismo
                # agricultor; el UniqueConstraint parcial es la última barrera.
                try:
                    agricultor = Usuario.objects.select_related("fk_persona").select_for_update().get(pk=agricultor.pk)
                except Usuario.DoesNotExist:
                    raise NotFound({"fk_agricultor": "El agricultor especificado no existe o está inactivo."}) from None
                if not agricultor.estado:
                    raise ValidationError({"fk_agricultor": "El agricultor especificado no existe o está inactivo."})
                if not agricultor.tiene_rol(AGRICULTOR):
                    raise ValidationError({"fk_agricultor": "El agricultor especificado no tiene rol Agricultor."})
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
            logger.exception("IntegrityError al guardar recolección (detalle):")
            if _constraint_violada(exc) != "uniq_recoleccion_activa_agricultor_fecha":
                raise
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
        if "estado" in request.data:
            raise ValidationError({"estado": "Use /estado/ o /cancelar/ para cambiar el estado."})
        # Capas que protegen la unicidad en partial_update:
        # 1. Pre-check del serializer (UX, sin lock del agricultor).
        # 2. UniqueConstraint parcial en BD (garantía final; IntegrityError -> 400
        #    discriminado por constraint name).
        # A diferencia de create, aquí NO hay lock del agricultor porque el
        # constraint cubre la unicidad; el lock de la fila (select_for_update)
        # serializa PATCH concurrentes sobre la misma recolección.
        try:
            with transaction.atomic():
                recoleccion = self._get_recoleccion_locked(self.kwargs.get("pk"))
                # Re-check bajo el lock: evita TOCTOU entre get_object y save.
                if recoleccion.estado in ("en_ruta", "recolectado", "cancelado"):
                    raise ValidationError(
                        {"estado": f"No se puede editar una recolección en estado '{recoleccion.estado}'."}
                    )
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
                        raise NotFound(
                            {"fk_agricultor": "El agricultor especificado no existe o está inactivo."}
                        ) from None
                    if not agricultor_nuevo.estado:
                        raise ValidationError(
                            {"fk_agricultor": "El agricultor especificado no existe o está inactivo."}
                        )
                    if not agricultor_nuevo.tiene_rol(AGRICULTOR):
                        raise ValidationError({"fk_agricultor": "El agricultor especificado no tiene rol Agricultor."})
                    # Reemplazar la instancia pre-lock por la bloqueada: evita TOCTOU
                    # y cachea fk_persona (select_related) para no disparar N+1 al
                    # re-serializar la respuesta.
                    serializer.validated_data["fk_agricultor"] = agricultor_nuevo
                serializer.save()
        except ValidationError:
            raise
        except IntegrityError as exc:
            logger.exception("IntegrityError al guardar recolección (detalle):")
            if _constraint_violada(exc) != "uniq_recoleccion_activa_agricultor_fecha":
                raise
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
