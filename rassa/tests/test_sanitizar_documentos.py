import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from rassa.models import Documento


@override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp(prefix="rassa_docs_test_")))
class SanitizarDocumentosCommandTest(TestCase):
    def setUp(self):
        self.docs_dir = Path(settings.MEDIA_ROOT) / "documentos"
        if self.docs_dir.exists():
            shutil.rmtree(self.docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        (self.docs_dir / "abc_listen%20before%20i%20go.mp3").write_bytes(b"x")
        (self.docs_dir / "def_Green A - Tragedia de amor.mp3").write_bytes(b"x")
        (self.docs_dir / "seguro_audio.mp3").write_bytes(b"x")
        self.encoded = Documento.objects.create(
            fk_usuario=None,
            nombre_documento="listen before i go.mp3",
            url_documento="documentos/abc_listen%20before%20i%20go.mp3",
            tipo_documento="audio",
        )
        self.spaced = Documento.objects.create(
            fk_usuario=None,
            nombre_documento="Green A - Tragedia de amor.mp3",
            url_documento="documentos/def_Green A - Tragedia de amor.mp3",
            tipo_documento="audio",
        )
        self.safe = Documento.objects.create(
            fk_usuario=None,
            nombre_documento="seguro_audio.mp3",
            url_documento="documentos/seguro_audio.mp3",
            tipo_documento="audio",
        )

    def test_renames_files_and_updates_db(self):
        call_command("sanitizar_documentos")
        self.encoded.refresh_from_db()
        self.spaced.refresh_from_db()
        self.safe.refresh_from_db()

        self.assertEqual(
            self.encoded.url_documento,
            "documentos/abc_listen_20before_20i_20go.mp3",
        )
        self.assertEqual(
            self.spaced.url_documento,
            "documentos/def_Green_A_-_Tragedia_de_amor.mp3",
        )
        self.assertEqual(self.safe.url_documento, "documentos/seguro_audio.mp3")

        self.assertTrue(
            (self.docs_dir / "abc_listen_20before_20i_20go.mp3").is_file()
        )
        self.assertTrue(
            (self.docs_dir / "def_Green_A_-_Tragedia_de_amor.mp3").is_file()
        )
        self.assertTrue((self.docs_dir / "seguro_audio.mp3").is_file())
        self.assertFalse(
            (self.docs_dir / "abc_listen%20before%20i%20go.mp3").exists()
        )
        self.assertFalse(
            (self.docs_dir / "def_Green A - Tragedia de amor.mp3").exists()
        )

    def test_dry_run_does_not_rename(self):
        call_command("sanitizar_documentos", "--dry-run")
        self.encoded.refresh_from_db()
        self.assertEqual(
            self.encoded.url_documento,
            "documentos/abc_listen%20before%20i%20go.mp3",
        )
        self.assertTrue(
            (self.docs_dir / "abc_listen%20before%20i%20go.mp3").is_file()
        )

    def test_missing_file_is_skipped_without_crashing(self):
        (self.docs_dir / "abc_listen%20before%20i%20go.mp3").unlink()
        call_command("sanitizar_documentos")
        self.encoded.refresh_from_db()
        self.assertEqual(
            self.encoded.url_documento,
            "documentos/abc_listen%20before%20i%20go.mp3",
        )

    def test_sanitize_filename_rule(self):
        from rassa.management.commands.sanitizar_documentos import sanitize_filename

        self.assertEqual(sanitize_filename("café (tarde).mp3"), "caf_tarde.mp3")
        self.assertEqual(
            sanitize_filename("listen%20before%20i%20go.mp3"),
            "listen_20before_20i_20go.mp3",
        )
