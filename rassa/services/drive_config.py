"""Configuración del servicio de Google Drive.

Constantes centralizadas para validación de archivos,
subida a Drive y manejo de errores de la API.
"""

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

MAGIC_BYTES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF",
    "image/gif": b"GIF8",
}

MB = 1024 * 1024
MAX_FILE_SIZE_MB = 10
HEADER_READ_SIZE = 16
MAX_FILENAME_LENGTH = 200
API_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2
RETRYABLE_STATUS_CODES = (429, 500, 502, 503)
