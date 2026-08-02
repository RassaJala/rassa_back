# Permite múltiples Pago con fk_pedido IS NULL (pagos de liquidación RASSA→agricultor).
# Antes: nulls_distinct=False bloqueaba el segundo pago de liquidación con IntegrityError.
# La unicidad real del constraint ("un pago por pedido") se mantiene cuando fk_pedido IS NOT NULL.
#
# IMPORTANTE: Requiere PostgreSQL >= 15. La sintaxis `UNIQUE NULLS DISTINCT` se
# introdujo en PG 15. En PG<15 la migración falla con `syntax error at or near
# "DISTINCT"`. Validar la versión del servidor antes de desplegar.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rassa", "0012_pago_folio_default"),
        ("rassa", "0017_merge_20260722_1151"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="pago",
            name="unique_pago_per_pedido",
        ),
        migrations.AddConstraint(
            model_name="pago",
            constraint=models.UniqueConstraint(
                fields=("fk_pedido",), name="unique_pago_per_pedido", nulls_distinct=True
            ),
        ),
    ]
