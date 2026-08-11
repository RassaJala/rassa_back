"""Management command: cancela pedidos pendientes expirados y restaura su stock.

Uso:
    python manage.py expirar_pedidos

Idempotente: solo toca pedidos en estado "pendiente" cuya fecha_expiracion ya
paso. Puede ejecutarse repetidamente (cron) sin efectos laterales.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from rassa.blueprints.pedido.views import _restaurar_stock_pedido
from rassa.models import EstadoPedido, HistorialEstadoPedido, PedidoCabecera

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cancela pedidos pendientes cuya fecha_expiracion ya paso y restaura el stock."

    def handle(self, *args, **options):
        # R1.4: el lookup del estado cancelado se hace ANTES del bloque atómico
        # para que el fallo sea ruidoso y limpio (CommandError), no un rollback vacío.
        try:
            cancelado = EstadoPedido.objects.get(tipo_estado="cancelado")
        except EstadoPedido.DoesNotExist:
            logger.error("Estado 'cancelado' no configurado en la base de datos")
            raise CommandError(
                "El estado 'cancelado' no está configurado en la base de datos. "
                "Ejecute el seed de estados."
            ) from None

        count = 0
        with transaction.atomic():
            expirados = (
                PedidoCabecera.objects.select_for_update()
                .select_related("fk_estado")
                .filter(fk_estado__tipo_estado="pendiente", fecha_expiracion__lt=timezone.now())
            )

            for pedido in expirados:
                # Mismo restore de stock que el flujo de cancelación manual
                # (pedido/views.py cambiar_estado) — helper compartido (_restaurar_stock_pedido).
                _restaurar_stock_pedido(pedido)

                estado_anterior = pedido.fk_estado
                pedido.fk_estado = cancelado
                pedido.save(update_fields=["fk_estado"])

                # fk_cambiado_por=None: accion automatica, no hay usuario.
                HistorialEstadoPedido.objects.create(
                    fk_pedido=pedido,
                    fk_estado_anterior=estado_anterior,
                    fk_estado_nuevo=cancelado,
                    fk_cambiado_por=None,
                )

                logger.warning("Pedido %s expirado => cancelado automatico (stock restaurado)", pedido.pk)
                count += 1

        self.stdout.write(self.style.SUCCESS(f"{count} pedidos expirados cancelados."))
