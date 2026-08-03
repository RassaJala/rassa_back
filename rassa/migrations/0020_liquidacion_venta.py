# Agrega el modelo LiquidacionVenta (snapshot de pedidos por liquidación).
# Depende de la migración 0018 y crea las relaciones para liquidar pedidos.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rassa', '0014_populate_conversacion_fk_familia'),
        ('rassa', '0018_pago_unique_pedido_allow_null_distinct'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiquidacionVenta',
            fields=[
                ('id_liquidacion_venta', models.AutoField(primary_key=True, serialize=False)),
                ('monto_aportado', models.DecimalField(decimal_places=2, help_text='Total del pedido al momento de la liquidación (snapshot).', max_digits=10)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'liquidacion_venta',
                'ordering': ['id_liquidacion_venta'],
            },
        ),
        migrations.AddField(
            model_name='liquidacionventa',
            name='fk_liquidacion',
            field=models.ForeignKey(db_column='fk_liquidacion', on_delete=django.db.models.deletion.CASCADE, related_name='ventas', to='rassa.liquidacion'),
        ),
        migrations.AddField(
            model_name='liquidacionventa',
            name='fk_pedido',
            field=models.ForeignKey(db_column='fk_pedido', on_delete=django.db.models.deletion.PROTECT, related_name='liquidaciones', to='rassa.pedidocabecera'),
        ),
        migrations.AddConstraint(
            model_name='liquidacionventa',
            constraint=models.UniqueConstraint(fields=('fk_liquidacion', 'fk_pedido'), name='unique_liquidacion_venta_pedido'),
        ),
    ]
