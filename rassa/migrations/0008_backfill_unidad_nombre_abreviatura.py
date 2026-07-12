from django.db import migrations

ABREVIATURAS = {
    "Kilogramo": "kg",
    "Pieza": "pz",
    "Manojo": "mj",
    "Litro": "L",
    "Docena": "doc",
}


def backfill_unidad_nombre_abreviatura(apps, schema_editor):
    Unidad = apps.get_model("rassa", "Unidad")
    for unidad in Unidad.objects.all():
        if unidad.nombre and unidad.abreviatura:
            continue
        nombre = unidad.nombre or unidad.tipo
        if not nombre:
            continue
        unidad.nombre = nombre
        unidad.abreviatura = unidad.abreviatura or ABREVIATURAS.get(nombre, nombre[:20])
        unidad.save(update_fields=["nombre", "abreviatura"])


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0007_unidad_abreviatura_unidad_nombre_alter_unidad_tipo"),
    ]

    operations = [
        migrations.RunPython(backfill_unidad_nombre_abreviatura, migrations.RunPython.noop),
    ]
