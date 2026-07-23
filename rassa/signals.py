"""Signals para el registro automático de historial de estados de pedido.

El signal ``registrar_cambio_estado`` escucha ``post_save`` de ``PedidoCabecera``
y crea un registro en ``HistorialEstadoPedido`` cada vez que ``fk_estado`` cambia.

Nota sobre ``update_fields``:
    Cuando se guarda con ``save(update_fields=["fk_estado"])`` (como en
    ``PedidoViewSet.cambiar_estado``), Django NO dispara signals. El historial
    se crea inline en ese caso. Este signal actúa como safety net para cambios
    de estado que ocurran por otras vías (Django admin, management commands, etc.).
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from rassa.models import HistorialEstadoPedido, PedidoCabecera

logger = logging.getLogger(__name__)

_pre_estado_cache = {}


@receiver(pre_save, sender=PedidoCabecera)
def _capturar_estado_anterior(sender, instance, **kwargs):
    """Almacena el ``fk_estado`` anterior antes de que se guarde el registro."""
    if instance.pk:
        try:
            anterior = PedidoCabecera.objects.get(pk=instance.pk)
            _pre_estado_cache[instance.pk] = anterior.fk_estado_id
        except PedidoCabecera.DoesNotExist:
            _pre_estado_cache[instance.pk] = None
    else:
        _pre_estado_cache[instance.pk] = None


@receiver(post_save, sender=PedidoCabecera)
def registrar_cambio_estado(sender, instance, created, **kwargs):
    """Registra automáticamente cada cambio de estado en HistorialEstadoPedido.

    - Si el pedido es nuevo y tiene estado inicial → crea registro con
      ``fk_estado_anterior=None``.
    - Si el pedido existente cambió de estado → crea registro con
      ambos estados.
    - Si el estado no cambió → no hace nada.
    - Si se usó ``update_fields`` → Django no dispara este signal,
      el historial se crea inline en la vista.
    """
    estado_anterior = _pre_estado_cache.pop(instance.pk, None)
    estado_nuevo = instance.fk_estado_id

    if created and estado_nuevo is not None and estado_anterior is None:
        HistorialEstadoPedido.objects.create(
            fk_pedido=instance,
            fk_estado_anterior=None,
            fk_estado_nuevo_id=estado_nuevo,
        )
        logger.info(
            "Pedido #%s creado con estado %s (signal)",
            instance.pk,
            estado_nuevo,
        )
        return

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
