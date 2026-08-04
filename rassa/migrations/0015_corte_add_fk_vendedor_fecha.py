from django.db import migrations, models

import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0014_populate_conversacion_fk_familia"),
    ]

    operations = [
        migrations.AddField(
            model_name="corte",
            name="fk_vendedor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cortes",
                to="rassa.usuario",
            ),
        ),
        migrations.AddField(
            model_name="corte",
            name="fecha",
            field=models.DateField(default=django.utils.timezone.localdate),
        ),
        migrations.AddConstraint(
            model_name="corte",
            constraint=models.UniqueConstraint(fields=("fk_vendedor", "fecha"), name="unique_corte_vendedor_fecha"),
        ),
    ]
