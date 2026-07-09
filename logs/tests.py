from django.test import TestCase

from rassa.models import Log


class ActivityLogModelTests(TestCase):
    def test_create_log_with_required_fields(self):
        log = Log.objects.create(
            descripcion="test POST /api/algo/",
            ip="127.0.0.1",
            dispositivo="test-agent",
        )

        self.assertEqual(log.descripcion, "test POST /api/algo/")
        self.assertEqual(log.ip, "127.0.0.1")
        self.assertEqual(log.dispositivo, "test-agent")
        self.assertIsNotNone(log.creado_en)
        self.assertTrue(log.estado)

    def test_log_without_usuario(self):
        """fk_usuario es nullable, debe poder crearse sin él."""
        log = Log.objects.create(
            descripcion="delete /api/test/",
            ip="192.168.1.1",
            dispositivo="test",
        )

        self.assertIsNone(log.fk_usuario)

    def test_log_str_method(self):
        log = Log.objects.create(
            descripcion="create POST /api/items/",
            ip="10.0.0.1",
            dispositivo="test",
        )

        self.assertIn("Log #", str(log))
        self.assertIn(str(log.id_log), str(log))
