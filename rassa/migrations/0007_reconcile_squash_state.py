# Reconcile migration state: register the squash migration and all its
# replaced migrations as applied so Django resolves the graph.
#
# The original migration files (0007-0017) were removed after squashing.
# Without them, Django cannot resolve 0007_squash_all_branches via replaces.
# Since the schema already reflects all those operations, we mark them as
# applied directly to unblock 0008_productoimagen_eliminar_pendiente.

from datetime import datetime, timezone

from django.db import migrations


def register_replaced_migrations(apps, schema_editor):
    """Insert squash + replaced migration records so the graph resolves."""
    cursor = schema_editor.connection.cursor()
    applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

    # All migrations that should be recorded as applied (squash + its replacements)
    migrations_to_register = [
        "0007_squash_all_branches",
        "0007_add_producto_descripcion",
        "0007_unidad_abreviatura_unidad_nombre_alter_unidad_tipo",
        "0008_add_producto_precio_stock_unidad_imagen",
        "0008_backfill_unidad_nombre_abreviatura",
        "0009_alter_publicacionsemanal_estado",
        "0009_localidad_estado_municipio_estado",
        "0010_alter_productosemanal_fk_producto_and_more",
        "0011_merge_0009_localidad_estado_and_publicacion",
        "0012_alter_familiausuario_fk_usuario",
        "0012_mensaje_editado",
        "0012_alter_productoimagen_options_productoimagen_orden",
        "0012_merge_producto_and_main",
        "0013_add_productoimagen_archivo",
        "0013_alter_producto_fk_categoria",
        "0013_merge_20260718_1323",
        "0014_add_unique_es_principal_constraint",
        "0014_productoimagen_url_only",
        "0015_add_producto_imagen_drive_file_id",
        "0015_productoimagen_squash_and_drive_file_id",
        "0016_merge_20260719_1534",
        "0017_merge_20260722_1151",
    ]

    # Check which are already applied
    cursor.execute(
        "SELECT name FROM django_migrations WHERE app = %s", ("rassa",)
    )
    already_applied = {row[0] for row in cursor.fetchall()}

    to_create = [name for name in migrations_to_register if name not in already_applied]
    for name in to_create:
        cursor.execute(
            "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
            ("rassa", name, applied_at),
        )


def reverse(apps, schema_editor):
    """No-op — these records should persist."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rassa", "0006_cascade_to_set_null_protect"),
    ]

    operations = [
        migrations.RunPython(register_replaced_migrations, reverse),
    ]
