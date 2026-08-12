"""Servicio de restauración de stock de pedidos.

Fuente unica de verdad para el restore de stock; usada por cambiar_estado y por
el comando expirar_pedidos sin cargar DRF.
"""

from django.db.models import F

from rassa.models import DetallePedido, ProductoSemanal


def restaurar_stock_pedido(pedido):
    """Restaura el stock de los detalles de un pedido (cancelación o expiración).

    Una regla de restore cambiada desvía el inventario en silencio si se aplica
    en un solo lugar, por eso vive aquí y no en la vista.
    """
    for detalle in DetallePedido.objects.filter(fk_pedido=pedido).select_related("fk_producto_semanal"):
        ps = detalle.fk_producto_semanal
        if ps:
            ProductoSemanal.objects.filter(pk=ps.pk).update(stock=F("stock") + detalle.cantidad)
