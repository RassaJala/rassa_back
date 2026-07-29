"""Migration graph consistency tests.

Verifies the migration graph loads without errors and contains only the
expected files (after the migration cleanup that removed stale individual
0007-0017 stubs).
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
