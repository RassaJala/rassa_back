"""Vistas para el módulo de Cortes."""

import logging
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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

    def get_serializer_class(self):
        if self.action == "create":
            return CorteCreateSerializer
        return CorteSerializer

    def get_queryset(self):
        qs = Corte.objects.all()
        usuario = getattr(self.request.user, "usuario", None)
        if usuario is None:
            return qs.none()

        rol = getattr(usuario, "fk_rol", None)
        nombre_rol = rol.nombre_rol if rol else None

        if nombre_rol == VENDEDOR:
            qs = qs.filter(fk_vendedor=usuario)
        elif nombre_rol != ADMIN:
            qs = qs.none()

        return qs

    def _monto_teorico(self, vendedor, fecha):
        total = (
            Pago.objects.filter(fk_pedido__fk_vendedor=vendedor, creado_en__date=fecha).aggregate(
                total=Sum("monto")
            )["total"]
        )
        return total or Decimal("0.00")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usuario = getattr(request.user, "usuario", None)
        if usuario is None:
            return Response(
                {"message": "No se encontró el perfil de usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha = serializer.validated_data["fecha"]
        monto_real = serializer.validated_data["monto_real"]
        monto_teorico = self._monto_teorico(usuario, fecha)

        if Corte.objects.filter(fk_vendedor=usuario, fecha=fecha).exists():
            return Response(
                {"message": f"Ya existe un corte para la fecha {fecha}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            corte = Corte.objects.create(
                fk_vendedor=usuario,
                fecha=fecha,
                monto_real=monto_real,
                monto_teorico=monto_teorico,
                estado="cerrado",
            )
        except IntegrityError:
            logger.warning("IntegrityError esperado (concurrencia) al crear corte para vendedor=%s fecha=%s", usuario.pk, fecha)
            return Response(
                {"message": f"Ya existe un corte para la fecha {fecha}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _log(
            request.user,
            f"corte_creado Corte #{corte.id_corte} fecha={fecha} "
            f"monto_real={monto_real} monto_teorico={monto_teorico}",
            request,
        )
        logger.info("Corte #%s creado para vendedor=%s fecha=%s", corte.id_corte, usuario.pk, fecha)

        return Response(CorteSerializer(corte).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def teorico(self, request):
        """GET /api/cortes/teorico/?fecha=YYYY-MM-DD — monto teórico del día."""
        fecha = timezone.localdate()
        raw_fecha = request.query_params.get("fecha")
        if raw_fecha:
            try:
                fecha = datetime.strptime(raw_fecha, "%Y-%m-%d").date()
            except ValueError as err:
                raise ValidationError({"fecha": "fecha debe tener formato YYYY-MM-DD."}) from err

        usuario = getattr(request.user, "usuario", None)
        monto_teorico = self._monto_teorico(usuario, fecha) if usuario is not None else Decimal("0.00")

        return Response({"fecha": str(fecha), "monto_teorico": str(monto_teorico)})
