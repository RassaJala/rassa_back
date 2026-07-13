import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# Abreviaturas conocidas del seed histórico (tipo → abreviatura).
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
        Unidad.objects.bulk_update(
            to_update,
            ["nombre", "abreviatura"],
            batch_size=BULK_BATCH_SIZE,
        )
    except Exception:
        for unidad in to_update:
            try:
                unidad.save(update_fields=["nombre", "abreviatura"])
            except Exception as exc:
                logger.error("Backfill failed for Unidad pk=%s: %s", unidad.pk, exc)
                raise


def reverse_backfill_unidad_nombre_abreviatura(apps, schema_editor):
    """Undo backfill rows where nombre/abreviatura mirror values derived from tipo."""
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

    if to_clear:
        Unidad.objects.bulk_update(
            to_clear,
            ["nombre", "abreviatura"],
            batch_size=BULK_BATCH_SIZE,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0007_unidad_abreviatura_unidad_nombre_alter_unidad_tipo"),
    ]

    operations = [
        migrations.RunPython(
            backfill_unidad_nombre_abreviatura,
            reverse_backfill_unidad_nombre_abreviatura,
        ),
    ]
