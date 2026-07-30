from django.db import migrations


def populate_fk_familia(apps, schema_editor):
    Familia = apps.get_model("rassa", "Familia")
    Conversacion = apps.get_model("rassa", "Conversacion")
    for conv in Conversacion.objects.filter(nombre__isnull=False).exclude(nombre=""):
        try:
            familia = Familia.objects.get(nombre_familia=conv.nombre)
            Conversacion.objects.filter(pk=conv.pk).update(fk_familia=familia)
        except Familia.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0009_conversacion_fk_familia"),
    ]

    operations = [
        migrations.RunPython(populate_fk_familia, migrations.RunPython.noop),
    ]
