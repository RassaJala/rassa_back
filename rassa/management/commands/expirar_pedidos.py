"""Management command: cancela pedidos pendientes expirados y restaura su stock.

Uso:
    python manage.py expirar_pedidos

Idempotente: solo toca pedidos en estado "pendiente" cuya fecha_expiracion ya
paso. Puede ejecutarse repetidamente (cron) sin efectos laterales.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from rassa.models import DetallePedido, EstadoPedido, HistorialEstadoPedido, PedidoCabecera, ProductoSemanal

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cancela pedidos pendientes cuya fecha_expiracion ya paso y restaura el stock."

    def handle(self, *args, **options):
        count = 0
        with transaction.atomic():
            expirados = (
                PedidoCabecera.objects.select_for_update()
                .select_related("fk_estado")
                .filter(fk_estado__tipo_estado="pendiente", fecha_expiracion__lt=timezone.now())
            )
            cancelado = EstadoPedido.objects.get(tipo_estado="cancelado")

            for pedido in expirados:
                # Mismo restore de stock que el flujo de cancelación manual
                # (pedido/views.py cambiar_estado).
                for detalle in DetallePedido.objects.filter(fk_pedido=pedido).select_related("fk_producto_semanal"):
                    producto_semanal = detalle.fk_producto_semanal
                    if producto_semanal:
                        ProductoSemanal.objects.filter(pk=producto_semanal.pk).update(
                            stock=F("stock") + detalle.cantidad
                        )

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
