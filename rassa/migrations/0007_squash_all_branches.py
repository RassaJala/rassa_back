# Squashed migration — replaces ALL migrations from 0007 through 0017.
# Consolidates all parallel branches (unidad/localidad + producto + chat + imagen) into one.
#
# Fresh DB: this single migration applies all operations at once.
# Existing DB: Django uses `replaces` to skip already-applied operations.

import logging

import django.db.models.deletion
from django.db import migrations, models

logger = logging.getLogger(__name__)

ABREVIATURAS = {
    "Kilogramo": "kg",
    "Pieza": "pz",
    "Manojo": "mj",
    "Litro": "L",
    "Docena": "doc",
}
MAX_ABBR_LEN = 20
BULK_BATCH_SIZE = 500


def _expected_abreviatura(nombre):
    return ABREVIATURAS.get(nombre, nombre[:MAX_ABBR_LEN])


def backfill_unidad_nombre_abreviatura(apps, schema_editor):
    Unidad = apps.get_model("rassa", "Unidad")
    to_update = []
    for unidad in Unidad.objects.all():
        if unidad.nombre and unidad.abreviatura:
            continue
        nombre = unidad.nombre or unidad.tipo
        if not nombre:
            continue
        unidad.nombre = nombre
        unidad.abreviatura = unidad.abreviatura or _expected_abreviatura(nombre)
        to_update.append(unidad)
    if not to_update:
        return
    try:
        Unidad.objects.bulk_update(to_update, ["nombre", "abreviatura"], batch_size=BULK_BATCH_SIZE)
    except Exception:
        for unidad in to_update:
            try:
                unidad.save(update_fields=["nombre", "abreviatura"])
            except Exception as exc:
                logger.error("Backfill failed for Unidad pk=%s: %s", unidad.pk, exc)
                raise


def reverse_backfill_unidad_nombre_abreviatura(apps, schema_editor):
    Unidad = apps.get_model("rassa", "Unidad")
    to_clear = []
    for unidad in Unidad.objects.all():
        if not unidad.tipo:
            continue
        expected_abbr = _expected_abreviatura(unidad.tipo)
        if unidad.nombre == unidad.tipo and unidad.abreviatura == expected_abbr:
            unidad.nombre = None
            unidad.abreviatura = None
            to_clear.append(unidad)
    if not to_clear:
        return
    try:
        Unidad.objects.bulk_update(to_clear, ["nombre", "abreviatura"], batch_size=BULK_BATCH_SIZE)
    except Exception:
        for unidad in to_clear:
            try:
                unidad.save(update_fields=["nombre", "abreviatura"])
            except Exception as exc:
                logger.error("Reverse backfill failed for Unidad pk=%s: %s", unidad.pk, exc)
                raise


class Migration(migrations.Migration):
    replaces = [
        ("rassa", "0007_add_producto_descripcion"),
        ("rassa", "0007_unidad_abreviatura_unidad_nombre_alter_unidad_tipo"),
        ("rassa", "0008_add_producto_precio_stock_unidad_imagen"),
        ("rassa", "0008_backfill_unidad_nombre_abreviatura"),
        ("rassa", "0009_alter_publicacionsemanal_estado"),
        ("rassa", "0009_localidad_estado_municipio_estado"),
        ("rassa", "0010_alter_productosemanal_fk_producto_and_more"),
        ("rassa", "0011_merge_0009_localidad_estado_and_publicacion"),
        ("rassa", "0012_alter_familiausuario_fk_usuario"),
        ("rassa", "0012_mensaje_editado"),
        ("rassa", "0012_alter_productoimagen_options_productoimagen_orden"),
        ("rassa", "0012_merge_producto_and_main"),
        ("rassa", "0013_add_productoimagen_archivo"),
        ("rassa", "0013_alter_producto_fk_categoria"),
        ("rassa", "0013_merge_20260718_1323"),
        ("rassa", "0014_add_unique_es_principal_constraint"),
        ("rassa", "0014_productoimagen_url_only"),
        ("rassa", "0015_add_producto_imagen_drive_file_id"),
        ("rassa", "0015_productoimagen_squash_and_drive_file_id"),
        ("rassa", "0016_merge_20260719_1534"),
        ("rassa", "0017_merge_20260722_1151"),
    ]

    dependencies = [
        ("rassa", "0006_cascade_to_set_null_protect"),
    ]

    operations = [
        # === Unidad: add nombre, abreviatura, alter tipo ===
        migrations.AddField(
            model_name="unidad",
            name="abreviatura",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="unidad",
            name="nombre",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="unidad",
            name="tipo",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        # === Backfill unidad nombre/abreviatura (data migration) ===
        migrations.RunPython(
            backfill_unidad_nombre_abreviatura,
            reverse_backfill_unidad_nombre_abreviatura,
        ),
        # === Producto: add fields ===
        migrations.AddField(
            model_name="producto",
            name="descripcion",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="producto",
            name="fk_unidad",
            field=models.ForeignKey(
                blank=True,
                db_column="fk_unidad",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="rassa.unidad",
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="imagen",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="producto",
            name="precio",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="producto",
            name="stock",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="producto",
            name="fk_categoria",
            field=models.ForeignKey(
                db_column="fk_categoria",
                on_delete=django.db.models.deletion.PROTECT,
                to="rassa.categoriaproducto",
            ),
        ),
        # === Localidad / Municipio: add estado ===
        migrations.AddField(
            model_name="localidad",
            name="estado",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="municipio",
            name="estado",
            field=models.BooleanField(default=True),
        ),
        # === PublicacionSemana: alter estado ===
        migrations.AlterField(
            model_name="publicacionsemanal",
            name="estado",
            field=models.CharField(
                choices=[
                    ("borrador", "Borrador"),
                    ("publicado", "Publicado"),
                    ("cerrado", "Cerrado"),
                    ("cancelado", "Cancelado"),
                ],
                default="borrador",
                max_length=20,
            ),
        ),
        # === ProductoSemanal: alter fk_producto + unique constraint ===
        migrations.AlterField(
            model_name="productosemanal",
            name="fk_producto",
            field=models.ForeignKey(
                db_column="fk_producto",
                on_delete=django.db.models.deletion.PROTECT,
                to="rassa.producto",
            ),
        ),
        migrations.AddConstraint(
            model_name="publicacionsemanal",
            constraint=models.UniqueConstraint(
                fields=("fk_agricultor", "semana"),
                name="unique_agricultor_semana",
            ),
        ),
        # === FamiliaUsuario: alter fk_usuario ===
        migrations.AlterField(
            model_name="familiausuario",
            name="fk_usuario",
            field=models.ForeignKey(
                db_column="fk_usuario",
                on_delete=django.db.models.deletion.CASCADE,
                to="rassa.usuario",
            ),
        ),
        # === Mensaje: add editado ===
        migrations.AddField(
            model_name="mensaje",
            name="editado",
            field=models.BooleanField(default=False),
        ),
        # === ProductoImagen: options, orden, url, drive_file_id, constraint ===
        migrations.AlterModelOptions(
            name="productoimagen",
            options={"ordering": ["orden", "id_imagen"]},
        ),
        migrations.AddField(
            model_name="productoimagen",
            name="orden",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="productoimagen",
            name="url",
            field=models.URLField(max_length=500),
        ),
        migrations.AddField(
            model_name="productoimagen",
            name="drive_file_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name="productoimagen",
            constraint=models.UniqueConstraint(
                condition=models.Q(es_principal=True),
                fields=["fk_producto"],
                name="unique_es_principal_per_producto",
            ),
        ),
    ]
