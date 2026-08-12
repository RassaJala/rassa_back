"""Backfill fecha_expiracion de pedidos pendientes existentes.

Review 4R C2 (PR #77): los pedidos pre-PR tienen fecha_expiracion=NULL y el
filtro fecha_expiracion__lt=now los excluye para SIEMPRE, bloqueando el limite
de credito con su stock descontado. Se setea creado_en + PEDIDO_EXPIRACION_HORAS
(48h, regla C-A1) en los pendientes existentes sin fecha.
"""

from datetime import timedelta

from django.conf import settings
from django.db import migrations, models


def backfill_fecha_expiracion(apps, schema_editor):
    PedidoCabecera = apps.get_model("rassa", "PedidoCabecera")
    EstadoPedido = apps.get_model("rassa", "EstadoPedido")
    horas = getattr(settings, "PEDIDO_EXPIRACION_HORAS", 48)
    try:
        pendiente = EstadoPedido.objects.get(tipo_estado="pendiente")
    except EstadoPedido.DoesNotExist:
        return
    PedidoCabecera.objects.filter(fk_estado=pendiente, fecha_expiracion__isnull=True).update(
        fecha_expiracion=models.F("creado_en") + timedelta(hours=horas)
    )


class Migration(migrations.Migration):
    dependencies = [("rassa", "0027_add_fk_pedido_to_merma")]
    operations = [
        migrations.RunPython(backfill_fecha_expiracion, migrations.RunPython.noop),
    ]
