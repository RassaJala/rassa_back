from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from rassa.services.google_drive import (
    MAX_FILE_SIZE_MB,
    _execute_with_retry,
    _sanitize_filename,
    _validate_magic_bytes,
    delete_file,
    upload_image,
)


class SanitizeFilenameTests(SimpleTestCase):
    def test_removes_directory_traversal(self):
        result = _sanitize_filename("../../etc/passwd")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)

    def test_strips_control_characters(self):
        result = _sanitize_filename("image.jpg\r\nFORGED")
        self.assertNotIn("\r", result)
        self.assertNotIn("\n", result)

    def test_limits_length(self):
        long_name = "a" * 300 + ".jpg"
        result = _sanitize_filename(long_name)
        self.assertLessEqual(len(result), 200)

    def test_replaces_dangerous_characters(self):
        result = _sanitize_filename("my file (1).jpg")
        self.assertNotIn("(", result)
        self.assertNotIn(")", result)
        self.assertNotIn(" ", result)

    def test_handles_dotfile(self):
        result = _sanitize_filename(".hidden")
        self.assertEqual(result, "unnamed_file")

    def test_handles_empty_name(self):
        result = _sanitize_filename("")
        self.assertEqual(result, "unnamed_file")

    def test_preserves_valid_name(self):
        result = _sanitize_filename("tomate.jpg")
        self.assertEqual(result, "tomate.jpg")

    def test_preserves_valid_name_with_underscores(self):
        result = _sanitize_filename("mi_foto_v2.png")
        self.assertEqual(result, "mi_foto_v2.png")


class ValidateMagicBytesTests(SimpleTestCase):
    def _make_file(self, content, content_type):
        return SimpleUploadedFile("test", content, content_type=content_type)

    def test_valid_jpeg(self):
        f = self._make_file(b"\xff\xd8\xff\xe0" + b"\x00" * 12, "image/jpeg")
        self.assertTrue(_validate_magic_bytes(f, "image/jpeg"))

    def test_valid_png(self):
        f = self._make_file(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png")
        self.assertTrue(_validate_magic_bytes(f, "image/png"))

    def test_valid_webp(self):
        f = self._make_file(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 4, "image/webp")
        self.assertTrue(_validate_magic_bytes(f, "image/webp"))

    def test_valid_gif(self):
        f = self._make_file(b"GIF89a" + b"\x00" * 10, "image/gif")
        self.assertTrue(_validate_magic_bytes(f, "image/gif"))

    def test_jpeg_with_png_magic_rejected(self):
        f = self._make_file(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/jpeg")
        self.assertFalse(_validate_magic_bytes(f, "image/jpeg"))

    def test_html_with_jpeg_content_type_rejected(self):
        html_content = b"<script>alert(1)</script>" + b"\x00" * 10
        f = self._make_file(html_content, "image/jpeg")
        self.assertFalse(_validate_magic_bytes(f, "image/jpeg"))

    def test_empty_file_rejected(self):
        f = self._make_file(b"", "image/jpeg")
        self.assertFalse(_validate_magic_bytes(f, "image/jpeg"))

    def test_truncated_jpeg_rejected(self):
        f = self._make_file(b"\xff\xd8", "image/jpeg")
        self.assertFalse(_validate_magic_bytes(f, "image/jpeg"))


class UploadImageTests(SimpleTestCase):
    def _make_image(self, content_type="image/jpeg"):
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 1024
        return SimpleUploadedFile("test.jpg", content, content_type=content_type)

    @patch("rassa.services.google_drive._get_drive_service")
    def test_upload_returns_url_and_file_id(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files().create().execute.return_value = {
            "id": "abc123",
            "webViewLink": "https://drive.google.com/file/d/abc123",
        }
        mock_service.permissions().create().execute.return_value = {}

        with patch("rassa.services.google_drive.config", return_value="fake_folder_id"):
            url, file_id = upload_image(self._make_image(), "test.jpg")

        self.assertEqual(file_id, "abc123")
        self.assertIn("abc123", url)

    @patch("rassa.services.google_drive.config", return_value="")
    @patch("rassa.services.google_drive.settings.GOOGLE_DRIVE_FOLDER_ID", None)
    def test_raises_when_folder_id_missing(self, *_):
        with self.assertRaises(ValueError) as ctx:
            upload_image(self._make_image(), "test.jpg")
        self.assertIn("GOOGLE_DRIVE_FOLDER_ID", str(ctx.exception))

    @patch("rassa.services.google_drive.config", return_value="folder")
    def test_rejects_invalid_content_type(self, _):
        f = SimpleUploadedFile("test.exe", b"\x00" * 100, content_type="application/exe")
        with self.assertRaises(ValueError) as ctx:
            upload_image(f, "test.exe")
        self.assertIn("no permitido", str(ctx.exception))

    @patch("rassa.services.google_drive.config", return_value="folder")
    def test_rejects_magic_bytes_mismatch(self, _):
        f = SimpleUploadedFile("fake.jpg", b"<html>" + b"\x00" * 100, content_type="image/jpeg")
        with self.assertRaises(ValueError) as ctx:
            upload_image(f, "fake.jpg")
        self.assertIn("no coincide", str(ctx.exception))

    @patch("rassa.services.google_drive.config", return_value="folder")
    def test_rejects_oversized_file(self, _):
        big_content = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
        f = SimpleUploadedFile("big.jpg", big_content, content_type="image/jpeg")
        with self.assertRaises(ValueError) as ctx:
            upload_image(f, "big.jpg")
        self.assertIn("tamaño máximo", str(ctx.exception))


class DeleteFileTests(SimpleTestCase):
    @patch("rassa.services.google_drive._get_drive_service")
    def test_deletes_file(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        delete_file("abc123")
        mock_service.files.assert_called_once()
        mock_service.files().delete.assert_called_with(fileId="abc123")
        mock_service.files().delete().execute.assert_called_once()

    def test_raises_on_empty_file_id(self):
        with self.assertRaises(ValueError):
            delete_file("")

    @patch("rassa.services.google_drive._get_drive_service")
    def test_raises_on_api_error(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files().delete().execute.side_effect = RuntimeError("API error")

        with self.assertRaises(RuntimeError):
            delete_file("abc123")

    @patch("rassa.services.google_drive.time.sleep")
    @patch("rassa.services.google_drive._get_drive_service")
    def test_delete_retries_on_429(self, mock_get_service, mock_sleep):
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        resp = MagicMock()
        resp.status = 429
        error_429 = HttpError(resp, b"rate limited")

        call_count = 0

        def execute_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error_429
            return {}

        mock_service.files().delete().execute.side_effect = execute_side_effect

        delete_file("abc123")
        self.assertEqual(call_count, 2)
        mock_sleep.assert_called_once()

    @patch("rassa.services.google_drive.time.sleep")
    @patch("rassa.services.google_drive._get_drive_service")
    def test_delete_retries_on_500(self, mock_get_service, mock_sleep):
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        resp = MagicMock()
        resp.status = 500
        error_500 = HttpError(resp, b"server error")

        call_count = 0

        def execute_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise error_500
            return {}

        mock_service.files().delete().execute.side_effect = execute_side_effect

        delete_file("abc123")
        self.assertEqual(call_count, 3)

    @patch("rassa.services.google_drive.time.sleep")
    @patch("rassa.services.google_drive._get_drive_service")
    def test_delete_raises_after_exhausted_retries(self, mock_get_service, mock_sleep):
        from googleapiclient.errors import HttpError

        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        resp = MagicMock()
        resp.status = 500
        error_500 = HttpError(resp, b"server error")

        mock_service.files().delete().execute.side_effect = error_500

        with self.assertRaises(HttpError):
            delete_file("abc123")
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("rassa.services.google_drive.time.sleep")
    @patch("rassa.services.google_drive._get_drive_service")
    def test_delete_non_retryable_error_raises_immediately(self, mock_get_service, mock_sleep):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files().delete().execute.side_effect = ValueError("bad input")

        with self.assertRaises(ValueError):
            delete_file("abc123")
        mock_sleep.assert_not_called()


class ExecuteWithRetryTests(SimpleTestCase):
    @patch("rassa.services.google_drive.time.sleep")
    def test_succeeds_on_first_attempt(self, _mock_sleep):
        mock_request = MagicMock()
        mock_request.execute.return_value = {"id": "ok"}

        result = _execute_with_retry(lambda: mock_request)
        self.assertEqual(result, {"id": "ok"})
        _mock_sleep.assert_not_called()

    @patch("rassa.services.google_drive.time.sleep")
    def test_succeeds_after_retryable_error(self, _mock_sleep):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 429
        error_429 = HttpError(resp, b"rate limited")

        mock_request_ok = MagicMock()
        mock_request_ok.execute.return_value = {"id": "ok"}

        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_fail = MagicMock()
                mock_fail.execute.side_effect = error_429
                return mock_fail
            return mock_request_ok

        result = _execute_with_retry(factory)
        self.assertEqual(result, {"id": "ok"})
        _mock_sleep.assert_called_once()

    @patch("rassa.services.google_drive.time.sleep")
    def test_raises_after_exhausted_retries(self, _mock_sleep):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 500
        error_500 = HttpError(resp, b"server error")

        mock_request = MagicMock()
        mock_request.execute.side_effect = error_500

        with self.assertRaises(HttpError):
            _execute_with_retry(lambda: mock_request)
        self.assertEqual(_mock_sleep.call_count, 2)

    @patch("rassa.services.google_drive.time.sleep")
    def test_non_retryable_error_raises_immediately(self, _mock_sleep):
        mock_request = MagicMock()
        mock_request.execute.side_effect = ValueError("bad input")

        with self.assertRaises(ValueError):
            _execute_with_retry(lambda: mock_request)
        _mock_sleep.assert_not_called()

    @patch("rassa.services.google_drive.time.sleep")
    def test_retryable_exception_triggers_retry(self, _mock_sleep):
        mock_request_ok = MagicMock()
        mock_request_ok.execute.return_value = {"id": "ok"}

        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_fail = MagicMock()
                mock_fail.execute.side_effect = TimeoutError("timeout")
                return mock_fail
            return mock_request_ok

        result = _execute_with_retry(factory)
        self.assertEqual(result, {"id": "ok"})
        _mock_sleep.assert_called_once()


class UploadOrphanRollbackTests(SimpleTestCase):
    def _make_image(self):
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 1024
        return SimpleUploadedFile("test.jpg", content, content_type="image/jpeg")

    @patch("rassa.services.google_drive.delete_file")
    @patch("rassa.services.google_drive._get_drive_service")
    @patch("rassa.services.google_drive.config", return_value="fake_folder_id")
    def test_orphan_file_deleted_when_permissions_fail(self, _cfg, mock_get_service, mock_delete):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files().create().execute.return_value = {
            "id": "orphan123",
            "webViewLink": "https://drive.google.com/file/d/orphan123",
        }
        mock_service.permissions().create().execute.side_effect = RuntimeError("perm denied")

        with self.assertRaises(RuntimeError):
            upload_image(self._make_image(), "test.jpg")

        mock_delete.assert_called_once_with("orphan123")
