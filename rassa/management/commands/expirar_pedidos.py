"""Management command: cancela pedidos pendientes expirados y restaura su stock.

Uso:
    python manage.py expirar_pedidos

Idempotente: solo toca pedidos en estado "pendiente" cuya fecha_expiracion ya
paso. Puede ejecutarse repetidamente (cron) sin efectos laterales.

Cada pedido se procesa en su propia transacción (savepoint): si un pedido falla
se registra el ID y se continúa con el siguiente, de modo que el lote siempre
avanza parcialmente (C1, review 4R).
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction
from django.utils import timezone

from rassa.blueprints.pedido.services.stock import (
    restaurar_stock_pedido as _restaurar_stock_pedido,
)
from rassa.models import EstadoPedido, HistorialEstadoPedido, PedidoCabecera

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cancela pedidos pendientes cuya fecha_expiracion ya paso y restaura el stock."

    def handle(self, *args, **options):
        # R1.4: el lookup del estado cancelado se hace ANTES del loop para que el
        # fallo sea ruidoso y limpio (CommandError), no un rollback vacío.
        try:
            cancelado = EstadoPedido.objects.get(tipo_estado="cancelado")
        except EstadoPedido.DoesNotExist:
            logger.error("Estado 'cancelado' no configurado en la base de datos")
            raise CommandError(
                "El estado 'cancelado' no está configurado en la base de datos. Ejecute el seed de estados."
            ) from None

        expirados = list(
            PedidoCabecera.objects.filter(
                fk_estado__tipo_estado="pendiente",
                fecha_expiracion__lt=timezone.now(),
            ).values_list("pk", flat=True)
        )

        count = 0
        fallidos = []
        # C1 (review 4R): transacción POR PEDIDO (savepoint). Un fallo no revierte
        # el lote completo: se registra el ID fallido y se continúa con el siguiente.
        for pk in expirados:
            try:
                with transaction.atomic():
                    pedido = PedidoCabecera.objects.select_for_update().select_related("fk_estado").get(pk=pk)
                    # re-validar bajo lock: pudo cambiar entre el listado y el lock
                    if (
                        pedido.fk_estado.tipo_estado != "pendiente"
                        or not pedido.fecha_expiracion
                        or pedido.fecha_expiracion >= timezone.now()
                    ):
                        continue
                    # Mismo restore de stock que el flujo de cancelación manual
                    # (pedido/views.py cambiar_estado) — helper compartido en
                    # services/stock.py (R4: sin cargar DRF en el cron).
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
                    logger.warning("Pedido %s expirado => cancelado automatico (stock restaurado)", pk)
                    count += 1
            except DatabaseError as exc:
                logger.error("Pedido %s fallo al expirar (se reintentara en el proximo tick): %s", pk, exc)
                fallidos.append(pk)

        if fallidos:
            self.stdout.write(self.style.WARNING(f"{count} pedidos cancelados, {len(fallidos)} fallidos: {fallidos}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"{count} pedidos expirados cancelados."))
