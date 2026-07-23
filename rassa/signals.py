"""Signals para el registro automático de historial de estados de pedido.

El signal ``registrar_cambio_estado`` escucha ``post_save`` de ``PedidoCabecera``
y crea un registro en ``HistorialEstadoPedido`` cada vez que ``fk_estado`` cambia.

Nota sobre ``update_fields``:
    Django SÍ dispara ``pre_save``/``post_save`` aunque se use ``update_fields``.
    Por eso este signal se salta cuando detecta ``update_fields`` — el historial
    se crea inline en ``PedidoViewSet.cambiar_estado`` para incluir ``fk_cambiado_por``.
    Este signal actúa como safety net para cambios de estado por otras vías
    (Django admin, management commands, etc.).
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from rassa.models import HistorialEstadoPedido, PedidoCabecera

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=PedidoCabecera)
def _capturar_estado_anterior(sender, instance, **kwargs):
    """Almacena el ``fk_estado`` anterior como atributo temporal en la instancia."""
    if instance.pk:
        try:
            anterior = PedidoCabecera.objects.get(pk=instance.pk)
            instance._estado_anterior_id = anterior.fk_estado_id
        except PedidoCabecera.DoesNotExist:
            instance._estado_anterior_id = None
    else:
        instance._estado_anterior_id = None


@receiver(post_save, sender=PedidoCabecera)
def registrar_cambio_estado(sender, instance, created, **kwargs):
    """Registra automáticamente cada cambio de estado en HistorialEstadoPedido.

    - Si el pedido es nuevo (created) → no hace nada, el estado inicial se maneja
      en la vista o en la migración de datos.
    - Si el estado no cambió → no hace nada.
    - Si se usó ``update_fields`` → el historial se crea inline en la vista,
      este signal se salta para evitar duplicados.
    - Solo crea registros para cambios de estado por vías externas
      (Django admin, management commands, etc.).
    """
    update_fields = kwargs.get("update_fields")
    if update_fields is not None or created:
        return

    estado_anterior = getattr(instance, "_estado_anterior_id", None)
    estado_nuevo = instance.fk_estado_id

    if estado_anterior is not None and estado_nuevo is not None and estado_anterior != estado_nuevo:
        HistorialEstadoPedido.objects.create(
            fk_pedido=instance,
            fk_estado_anterior_id=estado_anterior,
            fk_estado_nuevo_id=estado_nuevo,
        )
        logger.info(
            "Pedido #%s: estado %s → %s (signal)",
            instance.pk,
            estado_anterior,
            estado_nuevo,
        )
