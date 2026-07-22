"""Signals para el registro automÃ¡tico de historial de estados de pedido.

El signal ``registrar_cambio_estado`` escucha ``post_save`` de ``PedidoCabecera``
y crea un registro en ``HistorialEstadoPedido`` cada vez que ``fk_estado`` cambia.

Uso del usuario actual:
    Las vistas deben llamar ``set_current_user(usuario)`` antes de guardar
    el pedido para que ``fk_cambiado_por`` se registre correctamente.
    Ejemplo::

        from rassa.signals import set_current_user

        set_current_user(request.user.usuario)
        pedido.save()
        set_current_user(None)
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from rassa.models import HistorialEstadoPedido, PedidoCabecera

logger = logging.getLogger(__name__)

_current_user = None


def set_current_user(usuario):
    """Establece el usuario actual para que el signal lo use en ``fk_cambiado_por``.

    Las vistas deben envolver el ``save()`` del pedido con::

        set_current_user(usuario)
        pedido.save()
        set_current_user(None)
    """
    global _current_user
    _current_user = usuario


def get_current_user():
    """Retorna el usuario actual (para uso interno del signal)."""
    return _current_user


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
    """Registra automÃ¡ticamente cada cambio de estado en HistorialEstadoPedido.

    - Si el pedido es nuevo y tiene estado inicial â†’ crea registro con
      ``fk_estado_anterior=None``.
    - Si el pedido existente cambiÃ³ de estado â†’ crea registro con
      ambos estados.
    - Si el estado no cambiÃ³ â†’ no hace nada.
    """
    estado_anterior = _pre_estado_cache.pop(instance.pk, None)
    estado_nuevo = instance.fk_estado_id

    if created and estado_nuevo is not None and estado_anterior is None:
        HistorialEstadoPedido.objects.create(
            fk_pedido=instance,
            fk_estado_anterior=None,
            fk_estado_nuevo_id=estado_nuevo,
            fk_cambiado_por=get_current_user(),
        )
        logger.info(
            "Pedido #%s creado con estado %s",
            instance.pk,
            estado_nuevo,
        )
        return

    if estado_anterior is not None and estado_nuevo is not None and estado_anterior != estado_nuevo:
        HistorialEstadoPedido.objects.create(
            fk_pedido=instance,
            fk_estado_anterior_id=estado_anterior,
            fk_estado_nuevo_id=estado_nuevo,
            fk_cambiado_por=get_current_user(),
        )
        logger.info(
            "Pedido #%s: estado %s â†’ %s",
            instance.pk,
            estado_anterior,
            estado_nuevo,
        )
