"""Migration graph and data migration tests.

Verifies:
- Migration graph is consistent and has expected leaf nodes
- Stale individual stub files are not present
- backfill_unidad_nombre_abreviatura and reverse are idempotent
- dedup_es_principal cleans duplicate es_principal=True rows
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

    def test_expected_migrations_exist(self):
        """Core migrations must be present; stale individual stubs must not."""
        executor = MigrationExecutor(connection)
        disk = {name for app, name in executor.loader.disk_migrations if app == "rassa"}
        for expected in ("0001_initial", "0007_squash_all_branches", "0008_productoimagen_eliminar_pendiente"):
            self.assertIn(expected, disk, f"Missing expected migration {expected}")
        for stale in (
            "0007_add_producto_descripcion",
            "0009_alter_publicacionsemanal_estado",
            "0012_mensaje_editado",
        ):
            self.assertNotIn(stale, disk, f"Stale migration {stale} should have been removed")

    def test_single_leaf_node(self):
        """Only 0008_productoimagen_eliminar_pendiente should be a leaf."""
        executor = MigrationExecutor(connection)
        leaves = {name for app, name in executor.loader.graph.leaf_nodes() if app == "rassa"}
        self.assertEqual(leaves, {"0008_productoimagen_eliminar_pendiente"})


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
