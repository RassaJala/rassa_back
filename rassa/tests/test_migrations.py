"""Migration graph and data migration tests.

Verifies:
- Migration graph is consistent
- Squash migration exists and replaces the 21 individual stubs
- 0008 depends on the squash (not orphaned)
- backfill_unidad_nombre_abreviatura and reverse are idempotent
- 0015 eliminates orphan Recoleccion rows (fk_agricultor NULL) before the
  SET NOT NULL so the migration does not fail with "column contains null values"
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigrationGraphTests(TransactionTestCase):
    """Validate the migration graph is consistent and has the expected nodes."""

    def test_graph_loads_without_conflicts(self):
        """Loading the migration graph should not raise InconsistentMigrationHistory."""
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        self.assertIsNotNone(executor.loader.graph)

    def test_squash_migration_exists_and_replaces_expected(self):
        """0007_squash_all_branches exists and replaces the 21 individual stubs."""
        executor = MigrationExecutor(connection)
        disk = {name for app, name in executor.loader.disk_migrations if app == "rassa"}
        self.assertIn("0007_squash_all_branches", disk)
        mig = executor.loader.get_migration_by_prefix("rassa", "0007_squash_all_branches")
        # It should replace all 21 individual migrations from 0007–0017
        expected_replaced = {
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
        }
        replaced = {name for app, name in mig.replaces if app == "rassa"}
        self.assertEqual(replaced, expected_replaced)

    def test_0008_depends_on_squash(self):
        """0008_productoimagen_eliminar_pendiente depends on 0007_squash_all_branches."""
        executor = MigrationExecutor(connection)
        mig = executor.loader.get_migration_by_prefix("rassa", "0008_productoimagen_eliminar_pendiente")
        deps = {name for app, name in mig.dependencies if app == "rassa"}
        self.assertIn("0007_squash_all_branches", deps)


class DataMigrationTests(TransactionTestCase):
    """Verify backfill and dedup functions are idempotent."""

    def _get_apps(self):
        from django.apps import apps

        return apps

    def _forward(self):
        import importlib

        mod = importlib.import_module("rassa.migrations.0007_squash_all_branches")
        mod.backfill_unidad_nombre_abreviatura(apps=self._get_apps(), schema_editor=None)

    def _reverse(self):
        import importlib

        mod = importlib.import_module("rassa.migrations.0007_squash_all_branches")
        mod.reverse_backfill_unidad_nombre_abreviatura(apps=self._get_apps(), schema_editor=None)

    def test_forward_populates_empty_names(self):
        Unidad = self._get_apps().get_model("rassa", "Unidad")
        u = Unidad.objects.create(tipo="Kilogramo")
        self._forward()
        u.refresh_from_db()
        self.assertEqual(u.nombre, "Kilogramo")
        self.assertEqual(u.abreviatura, "kg")

    def test_forward_skips_complete_records(self):
        Unidad = self._get_apps().get_model("rassa", "Unidad")
        u = Unidad.objects.create(tipo="Kilogramo", nombre="Kilo", abreviatura="kg")
        self._forward()
        u.refresh_from_db()
        self.assertEqual(u.nombre, "Kilo")
        self.assertEqual(u.abreviatura, "kg")

    def test_forward_reverse_idempotent(self):
        Unidad = self._get_apps().get_model("rassa", "Unidad")
        u = Unidad.objects.create(tipo="Docena")
        self._forward()
        u.refresh_from_db()
        self.assertEqual(u.nombre, "Docena")
        self.assertEqual(u.abreviatura, "doc")
        self._reverse()
        u.refresh_from_db()
        self.assertIsNone(u.nombre)
        self.assertIsNone(u.abreviatura)
        # Second forward should restore
        self._forward()
        u.refresh_from_db()
        self.assertEqual(u.nombre, "Docena")
        self.assertEqual(u.abreviatura, "doc")

    def test_reverse_skips_manual_entries(self):
        Unidad = self._get_apps().get_model("rassa", "Unidad")
        u = Unidad.objects.create(tipo="Kilogramo", nombre="Kilo", abreviatura="kg")
        self._reverse()
        u.refresh_from_db()
        self.assertEqual(u.nombre, "Kilo")  # not touched
        self.assertEqual(u.abreviatura, "kg")

    # dedup_es_principal is not needed as a data migration — the
    # 0007_squash_all_branches migration adds the unique constraint
    # declaratively via AddConstraint. On existing databases the constraint
    # is skipped by --fake; duplicates were already resolved by the original
    # 0014_add_unique_es_principal_constraint migration.


class Migration0015Tests(TransactionTestCase):
    """Verifica que la migración 0015 elimine las huérfanas antes del SET NOT NULL.

    El estado previo (0014) permitía fk_agricultor NULL; la migración 0015 lo
    vuelve NOT NULL, por lo que debe eliminar (o abortar) cualquier fila
    huérfana antes de aplicar el AlterField.

    IMPORTANTE: este test migra el esquema compartido de la BD de test en vivo
    (0016 -> 0014 -> 0015 -> 0016). Solo es seguro corriendo de forma
    secuencial: NO usar pytest-xdist (paraleliza workers sobre la misma BD y
    rompería el esquema a mitad de migración).
    """

    def test_0015_elimina_huerfanas_y_aplica_not_null(self):
        # La BD de test parte del estado final; bajar a 0014 revierte 0016 y 0015
        # (sus RunPython tienen reverse=noop, no borran datos).
        executor = MigrationExecutor(connection)
        executor.migrate([("rassa", "0014_populate_conversacion_fk_familia")])

        # Restaurar el esquema al estado final para no romper el resto de pruebas.
        # addCleanup corre tras el test y reporta su propio fallo sin enmascarar el
        # error principal (un finally podría tapar el fallo real de la migración).
        def restaurar_esquema():
            executor = MigrationExecutor(connection)
            leaf = next(iter(executor.loader.graph.leaf_nodes("rassa")))
            executor.migrate([leaf])

        self.addCleanup(restaurar_esquema)

        old_apps = executor.loader.project_state([("rassa", "0014_populate_conversacion_fk_familia")]).apps
        Recoleccion = old_apps.get_model("rassa", "Recoleccion")
        Recoleccion.objects.create(fk_agricultor=None, fecha_recoleccion="2026-01-01", estado="pendiente")
        self.assertTrue(Recoleccion.objects.filter(fk_agricultor__isnull=True).exists())

        executor = MigrationExecutor(connection)
        executor.migrate([("rassa", "0015_alter_recoleccion_fk_agricultor_and_more")])
        new_apps = executor.loader.project_state([("rassa", "0015_alter_recoleccion_fk_agricultor_and_more")]).apps
        RecoleccionNew = new_apps.get_model("rassa", "Recoleccion")
        # La huérfana se eliminó y el SET NOT NULL pudo aplicarse sin error.
        self.assertFalse(RecoleccionNew.objects.filter(fk_agricultor__isnull=True).exists())

    def test_0015_conserva_pendiente_sobre_recolectado_en_duplicado(self):
        """Verifica que cancelar_duplicados_legacy priorice el estado NO-terminal.

        Si un par legacy tiene una recolectado (id menor, ya completada) y una
        pendiente (id mayor, la programada real), debe sobrevivir la pendiente y
        cancelarse la recolectado. Antes se conservaba la de menor id y se
        destruía la cita real (criterio viejo: solo por id_recoleccion).
        """
        executor = MigrationExecutor(connection)
        executor.migrate([("rassa", "0014_populate_conversacion_fk_familia")])

        def restaurar_esquema():
            executor = MigrationExecutor(connection)
            leaf = next(iter(executor.loader.graph.leaf_nodes("rassa")))
            executor.migrate([leaf])

        self.addCleanup(restaurar_esquema)

        old_apps = executor.loader.project_state([("rassa", "0014_populate_conversacion_fk_familia")]).apps
        Rol = old_apps.get_model("rassa", "Rol")
        Persona = old_apps.get_model("rassa", "Persona")
        Usuario = old_apps.get_model("rassa", "Usuario")
        Recoleccion = old_apps.get_model("rassa", "Recoleccion")

        rol = Rol.objects.create(nombre_rol="Agricultor", descripcion="Agricultor")
        persona = Persona.objects.create(
            nombre="Juan",
            apellido_paterno="Perez",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle 1",
        )
        agricultor = Usuario.objects.create(
            fk_persona=persona,
            fk_rol=rol,
            telefono="1234567890",
            correo="agri@migracion.test",
        )

        # Mismo agricultor, misma fecha: la recolectado se crea PRIMERO (id menor).
        completada = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-01", estado="recolectado"
        )
        programada = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-01", estado="pendiente"
        )
        self.assertLess(completada.pk, programada.pk)

        # Par TODO no-terminal: dos pendientes, misma fecha -> sobrevive la menor id.
        no_term_1 = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-02", estado="pendiente"
        )
        no_term_2 = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-02", estado="en_ruta"
        )
        self.assertLess(no_term_1.pk, no_term_2.pk)

        # Par TODO terminal: dos recolectado, misma fecha -> sobrevive la menor id.
        term_1 = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-03", estado="recolectado"
        )
        term_2 = Recoleccion.objects.create(
            fk_agricultor=agricultor, fecha_recoleccion="2026-01-03", estado="recolectado"
        )
        self.assertLess(term_1.pk, term_2.pk)

        executor = MigrationExecutor(connection)
        executor.migrate([("rassa", "0015_alter_recoleccion_fk_agricultor_and_more")])
        new_apps = executor.loader.project_state([("rassa", "0015_alter_recoleccion_fk_agricultor_and_more")]).apps
        RecoleccionNew = new_apps.get_model("rassa", "Recoleccion")

        # La pendiente (id mayor, la programada real) sobrevive sin cambios.
        self.assertEqual(RecoleccionNew.objects.get(pk=programada.pk).estado, "pendiente")
        # La recolectado (id menor, terminal) se cancela para liberar el constraint.
        self.assertEqual(RecoleccionNew.objects.get(pk=completada.pk).estado, "cancelado")

        # Todo-no-terminal: sobrevive la menor id, se cancela la segunda.
        self.assertEqual(RecoleccionNew.objects.get(pk=no_term_1.pk).estado, "pendiente")
        self.assertEqual(RecoleccionNew.objects.get(pk=no_term_2.pk).estado, "cancelado")

        # Todo-terminal: sobrevive la menor id, se cancela la segunda.
        self.assertEqual(RecoleccionNew.objects.get(pk=term_1.pk).estado, "recolectado")
        self.assertEqual(RecoleccionNew.objects.get(pk=term_2.pk).estado, "cancelado")
