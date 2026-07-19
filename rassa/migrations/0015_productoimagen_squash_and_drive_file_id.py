# Squash de migraciones 0013 + 0014: ProductoImagen usa solo URL (Google Drive).
# Agrega drive_file_id para poder eliminar archivos huérfanos.

from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [
        ("rassa", "0013_add_productoimagen_archivo"),
        ("rassa", "0014_productoimagen_url_only"),
    ]

    dependencies = [
        ("rassa", "0013_merge_20260718_1323"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productoimagen",
            name="url",
            field=models.URLField(max_length=500),
        ),
        migrations.AddField(
            model_name="productoimagen",
            name="drive_file_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
