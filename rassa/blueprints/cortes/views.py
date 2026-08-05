"""Vistas para el módulo de Cortes."""

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from rassa.models import Corte, Pago
from rassa.permissions.role_permissions import ADMIN, VENDEDOR, IsAdminOrVendedor
from rassa.views import _log

from .serializers import CorteCreateSerializer, CorteSerializer

logger = logging.getLogger(__name__)


class CorteViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet para cortes de caja (list, retrieve, create)."""

    permission_classes = [IsAuthenticated, IsAdminOrVendedor]
    throttle_classes = [UserRateThrottle]

    def get_serializer_class(self):
        if self.action == "create":
            return CorteCreateSerializer
        return CorteSerializer

    def get_queryset(self):
        qs = Corte.objects.select_related("fk_vendedor__fk_persona").all()
        usuario = self._usuario_autenticado(self.request)
        if usuario is None:
            return qs.none()

        nombre_rol = self._rol_nombre(usuario)
        if nombre_rol == VENDEDOR:
            qs = qs.filter(fk_vendedor=usuario)
        elif nombre_rol != ADMIN:
            qs = qs.none()

        return qs

    def _usuario_autenticado(self, request):
        """Devuelve el perfil Usuario asociado a request.user, o None."""
        return getattr(request.user, "usuario", None)

    def _rol_nombre(self, usuario):
        """Nombre del rol del usuario, o None si no tiene rol asignado."""
        rol = getattr(usuario, "fk_rol", None)
        return rol.nombre_rol if rol else None

    def _monto_teorico(self, vendedor, fecha):
        # Solo pagos en efectivo. El nombre canónico es "Efectivo"
        # (id_tipo_pago=1 en seed_rassa_data.py); __iexact cubre variantes
        # manuales de mayúsculas ("efectivo") sin atar el filtro a un id numérico.
        # Límites en la zona horaria local (settings.TIME_ZONE), no en la zona de la
        # conexión (UTC): un pago a las 23:59 local pertenece al día local, no al siguiente.
        tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
        inicio = timezone.make_aware(datetime.combine(fecha, time.min), tz)
        fin = inicio + timedelta(days=1)
        total = Pago.objects.filter(
            fk_pedido__fk_vendedor=vendedor,
            fk_tipo__nombre__iexact="efectivo",
            creado_en__gte=inicio,
            creado_en__lt=fin,
        ).aggregate(total=Sum("monto"))["total"]
        return total or Decimal("0.00")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usuario = self._usuario_autenticado(request)
        if usuario is None:
            return Response(
                {"message": "No se encontró el perfil de usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha = serializer.validated_data["fecha"]
        monto_real = serializer.validated_data["monto_real"]

        try:
            with transaction.atomic():
                monto_teorico = self._monto_teorico(usuario, fecha)
                existente = Corte.objects.select_for_update().filter(fk_vendedor=usuario, fecha=fecha).first()
                if existente is not None:
                    return Response(
                        {"message": f"Ya existe un corte para la fecha {fecha}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                corte = Corte.objects.create(
                    fk_vendedor=usuario,
                    fecha=fecha,
                    monto_real=monto_real,
                    monto_teorico=monto_teorico,
                    estado="cerrado",
                )
        except IntegrityError:
            # race condition guard
            logger.warning(
                "IntegrityError esperado (concurrencia) al crear corte para vendedor=%s fecha=%s",
                usuario.pk,
                fecha,
            )
            return Response(
                {"message": f"Ya existe un corte para la fecha {fecha}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Audit trail estructurado (tabla Log): los campos del corte van como
        # pares key=value separados, no solo interpolados en texto plano.
        _log(
            request.user,
            f"corte_creado id_corte={corte.id_corte} vendedor_id={usuario.pk} fecha={fecha} "
            f"monto_real={monto_real} monto_teorico={monto_teorico} diferencia={corte.diferencia}",
            request,
        )

        return Response(CorteSerializer(corte).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def teorico(self, request):
        """GET /api/cortes/teorico/?fecha=YYYY-MM-DD — monto teórico del día."""
        fecha = timezone.localdate()
        raw_fecha = request.query_params.get("fecha")
        if raw_fecha:
            fecha = self._parsear_fecha(raw_fecha)

        usuario = self._usuario_autenticado(request)
        if usuario is None:
            monto_teorico = Decimal("0.00")
        else:
            # Solo este endpoint cachea (TTL 60s): es una lectura para la UI.
            # create() usa _monto_teorico() sin cache para no persistir un valor
            # desactualizado como snapshot del corte.
            cache_key = f"corte_monto_teorico_{usuario.pk}_{fecha}"
            cached = cache.get(cache_key)
            if cached is not None:
                monto_teorico = Decimal(cached)
            else:
                monto_teorico = self._monto_teorico(usuario, fecha)
                # Decimal no es JSON-serializable: se guarda como string.
                cache.set(cache_key, str(monto_teorico), 60)

        return Response({"fecha": str(fecha), "monto_teorico": str(monto_teorico)})

    def _parsear_fecha(self, raw_fecha):
        try:
            return datetime.strptime(raw_fecha, "%Y-%m-%d").date()
        except ValueError as err:
            raise ValidationError({"fecha": "fecha debe tener formato YYYY-MM-DD."}) from err
