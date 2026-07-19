# Migra ProductoImagen a solo URL (Google Drive) — combina agregar y quitar archivo.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0012_mensaje_editado"),
        ("rassa", "0013_add_productoimagen_archivo"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="productoimagen",
            name="archivo",
        ),
        migrations.AlterField(
            model_name="productoimagen",
            name="url",
            field=models.URLField(max_length=500),
        ),
    ]
