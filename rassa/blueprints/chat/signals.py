"""Receptores de señales para sincronización Familias → Chat."""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from rassa.models import Familia

from .services import chat_sync


@receiver(post_save, sender=Familia)
def _sync_family_chat_name_receiver(sender, instance, created, **kwargs):
    """Cuando se edita una familia (no crear), sincroniza el nombre del chat familiar.

    sync_family_chat_name es no-op si no hay conv activa o si nombre_override=True.
    on_commit evita disparar la sync si la tx de Familias aborta.
    """
    if created:
        return
    transaction.on_commit(lambda: chat_sync.sync_family_chat_name(instance.pk, instance.nombre_familia))
