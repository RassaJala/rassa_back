from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from googleapiclient.errors import HttpError

from rassa.models import CategoriaProducto, Producto, ProductoImagen


def _make_resp(status, reason="Error"):
    """Build a minimal mock resp object for HttpError."""
    resp = type("Resp", (), {"status": status, "reason": reason})()
    return resp


class CleanupOrphanDriveFilesTest(TestCase):
    def setUp(self):
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas", descripcion="test", estado=True,
        )
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.category,
            estado=True,
        )
        self.imagen = ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/test.jpg",
            drive_file_id="drive_abc123",
            eliminar_pendiente=True,
        )
        self.out = StringIO()

    # ── DRY RUN ──────────────────────────────────────────────────

    def test_dry_run_no_modifica_db(self):
        """dry_run=True no elimina ni Drive ni DB."""
        call_command("cleanup_orphan_drive_files", stdout=self.out)
        self.assertTrue(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_dry_run_no_llama_delete_file(self):
        """dry_run=True no invoca delete_file de Drive."""
        with patch("rassa.management.commands.cleanup_orphan_drive_files.delete_file") as mock:
            call_command("cleanup_orphan_drive_files", stdout=self.out)
        mock.assert_not_called()

    def test_dry_run_muestra_pending(self):
        """dry_run=True muestra los archivos pendientes."""
        call_command("cleanup_orphan_drive_files", stdout=self.out)
        output = self.out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("1 image(s) pending", output)

    def test_no_pending_mensaje_success(self):
        """Sin archivos pendientes muestra mensaje de éxito."""
        ProductoImagen.objects.all().delete()
        call_command("cleanup_orphan_drive_files", stdout=self.out)
        output = self.out.getvalue()
        self.assertIn("No pending orphan files", output)

    # ── EXECUTE (--delete) ───────────────────────────────────────

    def test_delete_exitoso_elimina_imagen(self):
        """delete_file exitoso elimina el registro de DB."""
        with patch("rassa.management.commands.cleanup_orphan_drive_files.delete_file"):
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        self.assertFalse(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_delete_exitoso_llama_delete_file(self):
        """delete_file exitoso invoca a Drive con el file_id correcto."""
        with patch("rassa.management.commands.cleanup_orphan_drive_files.delete_file") as mock:
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        mock.assert_called_once_with("drive_abc123")

    def test_delete_fallido_mantiene_imagen(self):
        """Si delete_file falla, la imagen se mantiene en DB."""
        with patch(
            "rassa.management.commands.cleanup_orphan_drive_files.delete_file",
            side_effect=Exception("Drive timeout"),
        ):
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        self.assertTrue(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_delete_404_limpia_db(self):
        """Si Drive retorna 404 (archivo ya eliminado), se limpia la DB igual."""
        error = HttpError(
            _make_resp(404),
            b'{"error": {"code": 404, "message": "Not Found"}}',
        )
        with patch(
            "rassa.management.commands.cleanup_orphan_drive_files.delete_file",
            side_effect=error,
        ):
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        self.assertFalse(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())
        output = self.out.getvalue()
        self.assertIn("already gone from Drive", output)

    def test_delete_500_no_limpia_db(self):
        """Si Drive retorna 500, la imagen se mantiene en DB."""
        error = HttpError(
            _make_resp(500),
            b'{"error": {"code": 500, "message": "Internal Error"}}',
        )
        with patch(
            "rassa.management.commands.cleanup_orphan_drive_files.delete_file",
            side_effect=error,
        ):
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        self.assertTrue(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_sin_file_id_elimina_directamente(self):
        """Si drive_file_id está vacío, solo elimina el registro de DB."""
        self.imagen.drive_file_id = ""
        self.imagen.save(update_fields=["drive_file_id"])
        with patch("rassa.management.commands.cleanup_orphan_drive_files.delete_file") as mock:
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        mock.assert_not_called()
        self.assertFalse(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_varias_imagenes_conteo_correcto(self):
        """Verifica el conteo de deleted/failed con múltiples imágenes."""
        ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/test2.jpg",
            drive_file_id="drive_xyz789",
            eliminar_pendiente=True,
        )
        error = HttpError(
            _make_resp(500),
            b'{"error": {"code": 500, "message": "Internal Error"}}',
        )
        with patch(
            "rassa.management.commands.cleanup_orphan_drive_files.delete_file",
            side_effect=error,
        ):
            call_command("cleanup_orphan_drive_files", "--delete", stdout=self.out)
        output = self.out.getvalue()
        self.assertIn("Done: 0 deleted, 2 failed", output)
