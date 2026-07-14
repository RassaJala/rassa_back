"""Tests para el management command seed_rassa_data.

Verifica que el command corre sin errores, crea los registros esperados
y que --clear funciona correctamente.

Uso:
    python manage.py test rassa.tests.test_seed_rassa_data
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Max
from django.test import TestCase

from rassa.models import (
    DetallePedido,
    PedidoCabecera,
    Producto,
    Rol,
    Unidad,
    Usuario,
)

User = get_user_model()


class SeedRassaDataTest(TestCase):
    """Tests para el management command seed_rassa_data."""

    def test_seed_creates_records_without_errors(self):
        """El command corre sin errores y crea registros."""
        call_command("seed_rassa_data")

        self.assertGreater(Rol.objects.count(), 0)
        self.assertGreater(Usuario.objects.count(), 0)
        self.assertGreater(Producto.objects.count(), 0)
        self.assertGreater(PedidoCabecera.objects.count(), 0)

    def test_seed_creates_expected_records(self):
        """Crea los registros esperados (usuarios, productos, pedidos, etc.)."""
        call_command("seed_rassa_data")

        self.assertGreaterEqual(Rol.objects.count(), 4)
        self.assertGreaterEqual(Usuario.objects.count(), 12)
        self.assertGreaterEqual(Producto.objects.count(), 20)
        self.assertGreaterEqual(PedidoCabecera.objects.count(), 5)
        self.assertGreaterEqual(DetallePedido.objects.count(), 5)
        self.assertGreaterEqual(User.objects.count(), 12)

    def test_clear_removes_and_recreates_data(self):
        """--clear elimina datos y los recarga correctamente."""
        call_command("seed_rassa_data")

        initial_usuarios = Usuario.objects.count()
        initial_productos = Producto.objects.count()
        initial_pedidos = PedidoCabecera.objects.count()

        call_command("seed_rassa_data", "--clear")

        self.assertEqual(Usuario.objects.count(), initial_usuarios)
        self.assertEqual(Producto.objects.count(), initial_productos)
        self.assertEqual(PedidoCabecera.objects.count(), initial_pedidos)

    def test_seed_unidades_have_nombre_and_abreviatura(self):
        """Las unidades del seed exponen nombre y abreviatura para la API."""
        call_command("seed_rassa_data")

        kilogramo = Unidad.objects.get(nombre="Kilogramo", abreviatura="kg")
        self.assertEqual(kilogramo.nombre, "Kilogramo")
        self.assertEqual(kilogramo.abreviatura, "kg")

    def test_create_unidad_after_seed_does_not_duplicate_pk(self):
        """Tras el seed se puede crear una unidad nueva sin conflicto de ID."""
        call_command("seed_rassa_data")

        initial_count = Unidad.objects.count()
        max_id_before = Unidad.objects.aggregate(Max("id_unidad"))["id_unidad__max"]

        nueva = Unidad.objects.create(
            nombre="Gramo",
            abreviatura="g",
            tipo="Gramo",
            estado=True,
        )

        self.assertEqual(Unidad.objects.count(), initial_count + 1)
        self.assertEqual(nueva.id_unidad, max_id_before + 1)
