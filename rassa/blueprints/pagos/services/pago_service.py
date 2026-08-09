"""Funciones puras de ORM para pago: pago + recibo + avance de estado."""

from django.db import transaction

from rassa.models import HistorialEstadoPedido, Pago, Recibo


@transaction.atomic
def registrar_pago(pedido, tipo_id, monto, referencia, estado_entregado, usuario):
    """Crea el pago + su recibo y avanza el pedido a entregado.

    Atomico por si solo (nested-atomic seguro si el caller ya esta en una
    transaccion). El lock de fila del pedido queda a cargo del caller.
    """
    pago = Pago(fk_pedido=pedido, fk_tipo_id=tipo_id, monto=monto, referencia=referencia)
    pago.save()

    Recibo.objects.create(fk_pago=pago, fk_pedido=pedido, folio=f"R-{pago.folio}", monto=monto)

    estado_anterior = pedido.fk_estado
    pedido.fk_estado = estado_entregado
    pedido.save(update_fields=["fk_estado"])

    HistorialEstadoPedido.objects.create(
        fk_pedido=pedido,
        fk_estado_anterior=estado_anterior,
        fk_estado_nuevo=estado_entregado,
        fk_cambiado_por=usuario,
    )

    return pago
