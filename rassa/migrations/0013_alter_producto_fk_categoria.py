import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0012_merge_producto_and_main"),
    ]

    operations = [
        migrations.AlterField(
            model_name="producto",
            name="fk_categoria",
            field=models.ForeignKey(
                db_column="fk_categoria",
                on_delete=django.db.models.deletion.PROTECT,
                to="rassa.categoriaproducto",
            ),
        ),
    ]
