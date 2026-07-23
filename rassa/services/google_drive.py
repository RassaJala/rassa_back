"""Servicio para subir archivos a Google Drive usando OAuth2.

Requiere credenciales OAuth2 (Client ID + Client Secret) y un refresh token
obtenido mediante autorización del usuario.

Pasos para configurar:
1. Crear credenciales OAuth2 en Google Cloud Console
2. Ejecutar: python manage.py authorize_drive
3. Seguir las instrucciones para autorizar la app
4. El refresh token se guarda automáticamente en .env

Decisión de diseño — visibilidad de imágenes (W3):
Las imágenes subidas a Google Drive se hacen públicas automáticamente
(permiso "anyone -> reader"). Esto es intencional porque:

1. Es una app de marketplace agrícola: los clientes necesitan ver las
   fotos de los productos para comprar. Si las imágenes fueran privadas,
   las URLs no cargarían para usuarios externos.

2. Google Drive no es un CDN: sin permisos públicos, cada petición
   necesitaría un proxy con autenticación, lo cual agrega complejidad
   y costo innecesario.

3. Las URLs de Drive ya son "ocultas": no hay un listado público de
   imágenes. Solo se accede si se tiene la URL exacta.

4. El producto tiene estado: si el producto está inactivo, el frontend
   simplemente no muestra la imagen. La URL puede funcionar, pero nadie
   la va a visitar si el producto no está publicado.

Si en el futuro se necesita privacidad selectiva, se puede:
- Hacer las imágenes privadas por defecto y publicarlas solo cuando
  el producto pase a estado activo.
- Usar URLs firmadas con expiración.
- Configurar la visibilidad como un campo en el modelo Producto.

Limitaciones conocidas:
- Upload síncrono: bajo alta carga puede bloquear workers del servidor.
  Para escalar, migrar a Celery o tarea async.
- Sin circuit breaker: si Drive está caído, cada request espera
  retry + backoff antes de fallar. Pendiente implementar.
"""

import io
import logging
import os
import re
import tempfile
import threading
import time

from decouple import config
from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

from .drive_config import (
    ALLOWED_MIME_TYPES,
    API_TIMEOUT_SECONDS,
    HEADER_READ_SIZE,
    MAGIC_BYTES,
    MAX_FILE_SIZE_MB,
    MAX_FILENAME_LENGTH,
    MAX_RETRIES,
    MB,
    RETRY_BACKOFF_BASE,
    RETRYABLE_STATUS_CODES,
    SCOPES,
)

logger = logging.getLogger(__name__)

_service_cache = {"service": None}
_service_lock = threading.Lock()


def _get_credentials():
    """Construye credenciales OAuth2 desde variables de entorno.

    Returns:
        Credentials: Credenciales OAuth2 válidas.

    Raises:
        ValueError: Si faltan variables de entorno requeridas.
    """
    client_id = config("GOOGLE_DRIVE_CLIENT_ID", default=None) or getattr(settings, "GOOGLE_DRIVE_CLIENT_ID", None)
    client_secret = config("GOOGLE_DRIVE_CLIENT_SECRET", default=None) or getattr(
        settings, "GOOGLE_DRIVE_CLIENT_SECRET", None
    )
    refresh_token = config("GOOGLE_DRIVE_REFRESH_TOKEN", default=None) or getattr(
        settings, "GOOGLE_DRIVE_REFRESH_TOKEN", None
    )
    credentials_path = config("GOOGLE_DRIVE_CREDENTIALS_PATH", default=None) or getattr(
        settings, "GOOGLE_DRIVE_CREDENTIALS_PATH", None
    )

    if refresh_token and client_id and client_secret:
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

    if credentials_path:
        from google.oauth2.credentials import Credentials as FileCredentials

        creds = FileCredentials.from_authorized_user_file(credentials_path, SCOPES)
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
        return creds

    raise ValueError(
        "Google Drive credentials not configured. "
        "Set GOOGLE_DRIVE_REFRESH_TOKEN, GOOGLE_DRIVE_CLIENT_ID, "
        "and GOOGLE_DRIVE_CLIENT_SECRET in environment."
    )


def _get_drive_service():
    """Construye y retorna un servicio de Google Drive autenticado (con cache).

    Aplica API_TIMEOUT_SECONDS para evitar bloqueos indefinidos.
    Usa threading.Lock para ser seguro en WSGI multiproceso.

    Returns:
        Resource: Servicio de Google Drive autenticado.

    Raises:
        Exception: Si la autenticación falla.
    """
    if _service_cache["service"] is not None:
        return _service_cache["service"]

    with _service_lock:
        if _service_cache["service"] is not None:
            return _service_cache["service"]

        try:
            credentials = _get_credentials()
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            import httplib2

            http = httplib2.Http(timeout=API_TIMEOUT_SECONDS)
            service = build("drive", "v3", credentials=credentials, http=http)
            _service_cache["service"] = service
            return service
        except Exception as exc:
            error_type = type(exc).__name__
            logger.error("Error al autenticar con Google Drive: %s", error_type)
            raise


def _sanitize_filename(name):
    """Sanitiza el nombre del archivo para prevenir inyección y paths maliciosos.

    Args:
        name (str): Nombre original del archivo.

    Returns:
        str: Nombre sanitizado y seguro para usar en Drive.
    """
    name = os.path.basename(name)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[^a-zA-Z0-9._\-]", "_", name)
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH]
    if not name or name.startswith("."):
        name = "unnamed_file"
    return name


def _validate_magic_bytes(file, expected_type):
    """Valida que los bytes reales del archivo coincidan con el tipo MIME declarado.

    Args:
        file: Archivo con método seek() y read().
        expected_type (str): Tipo MIME esperado (ej: 'image/jpeg').

    Returns:
        bool: True si los magic bytes coinciden, False si no.
    """
    file.seek(0)
    header = file.read(HEADER_READ_SIZE)
    file.seek(0)

    magic = MAGIC_BYTES.get(expected_type)
    if magic is None:
        return False

    if expected_type == "image/webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"

    return header[: len(magic)] == magic


def _get_status_code(exc):
    """Extrae el código de estado HTTP de una excepción de la API de Drive.

    Args:
        exc: Excepción capturada de la API.

    Returns:
        int or None: Código de estado HTTP, o None si no está disponible.
    """
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    return getattr(resp, "status", None)


def _execute_with_retry(func, *args, **kwargs):
    """Ejecuta una función de la API de Drive con reintento y exponential backoff.

    Args:
        func: Función de la API de Drive a ejecutar.
        *args: Argumentos posicionales para la función.
        **kwargs: Argumentos de palabra clave para la función.

    Returns:
        dict: Respuesta de la API de Drive.

    Raises:
        Exception: Si después de MAX_RETRIES intentos sigue fallando.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs).execute(num_retries=0)
        except Exception as exc:
            last_exc = exc
            status_code = _get_status_code(exc)
            is_retryable = status_code in RETRYABLE_STATUS_CODES or isinstance(
                exc, (TimeoutError, ConnectionError, OSError)
            )
            if attempt < MAX_RETRIES and is_retryable:
                wait = RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "Drive API retry %d/%d after %.1fs (status=%s): %s",
                    attempt,
                    MAX_RETRIES,
                    wait,
                    status_code,
                    exc,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "Drive API error after %d attempts (status=%s): %s",
                    attempt,
                    status_code,
                    exc,
                )
                raise
    raise last_exc


def _validate_file(file, filename):
    """Valida un archivo antes de subirlo a Drive.

    Verifica tipo MIME, magic bytes y tamaño máximo.

    Args:
        file: Archivo subido (request.FILES['archivo']).
        filename (str): Nombre del archivo.

    Returns:
        str: content_type validado.

    Raises:
        ValueError: Si el archivo no es válido.
    """
    content_type = file.content_type
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Tipo de archivo no permitido: {content_type}. Formatos válidos: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )

    if not _validate_magic_bytes(file, content_type):
        raise ValueError(
            f"El contenido del archivo no coincide con el tipo {content_type}. "
            "Asegurate de que el archivo no esté corrupto."
        )

    file.seek(0, os.SEEK_END)
    file_size_mb = file.tell() / MB
    file.seek(0)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE_MB}MB.")

    return content_type


def _get_or_create_folder(service, name, parent_id):
    """Find or create a folder by name inside parent_id. Returns folder ID."""
    if not isinstance(parent_id, str) or not parent_id.strip():
        raise ValueError("parent_id must be a non-empty string")

    # Reject names with null bytes or control characters that can't be safely escaped
    if "\x00" in name:
        raise ValueError("Folder name contains null bytes")
    # Only allow alphanumeric, spaces, hyphens, underscores, and dots
    if not all(c.isalnum() or c in " -_." for c in name):
        raise ValueError(f"Folder name contains disallowed characters: {name!r}")

    # Escape Drive query special characters: \ ' ( ) and whitespace control
    safe_name = (
        name.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    query = (
        f"mimeType='application/vnd.google-apps.folder'"
        f" and name='{safe_name}'"
        f" and '{parent_id}' in parents"
        f" and trashed=false"
    )
    results = _execute_with_retry(service.files().list, q=query, fields="files(id)", spaces="drive")
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    folder_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = _execute_with_retry(service.files().create, body=folder_metadata, fields="id")
    return folder["id"]


def _upload_to_drive(service, tmp_path, content_type, safe_name, folder_id):
    """Sube un archivo temporal a Google Drive con retry.

    Args:
        service: Servicio de Google Drive autenticado.
        tmp_path (str): Ruta del archivo temporal.
        content_type (str): Tipo MIME del archivo.
        safe_name (str): Nombre sanitizado del archivo.
        folder_id (str): ID de la carpeta destino en Drive.

    Returns:
        str: file_id del archivo subido.

    Raises:
        Exception: Si la subida falla después de los reintentos.
    """
    file_metadata = {
        "name": safe_name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(tmp_path, mimetype=content_type, resumable=True)

    uploaded = _execute_with_retry(
        service.files().create,
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    )
    return uploaded.get("id")


def _set_public_permission(service, file_id):
    """Asigna permisos públicos de lectura a un archivo en Drive.

    Args:
        service: Servicio de Google Drive autenticado.
        file_id (str): ID del archivo en Drive.

    Raises:
        Exception: Si la asignación falla después de los reintentos.
    """
    _execute_with_retry(
        service.permissions().create,
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    )


def upload_image(file, filename, folder_id=None):
    """Sube una imagen a Google Drive y retorna la URL pública de descarga.

    Valida tipo MIME, magic bytes y tamaño del archivo antes de subir.
    Sanitiza el nombre del archivo para prevenir inyección.
    Limpia archivos temporales incluso si ocurre un error.

    Args:
        file: Archivo subido (request.FILES['archivo']).
        filename (str): Nombre del archivo (ej: 'tomate.jpg').
        folder_id (str, optional): ID de la carpeta de Drive.
            Si es None, usa GOOGLE_DRIVE_FOLDER_ID de .env.

    Returns:
        dict: {'url': str, 'file_id': str} con la URL y el ID del archivo en Drive.

    Raises:
        ValueError: Si el archivo no es válido, excede el tamaño máximo,
            o falta la configuración de carpeta.
    """
    if folder_id is None:
        folder_id = config("GOOGLE_DRIVE_FOLDER_ID", default=None) or getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID no está configurado.")

    safe_name = _sanitize_filename(filename)
    content_type = _validate_file(file, filename)

    service = _get_drive_service()

    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(safe_name)[1])
    with os.fdopen(fd, "wb") as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)

    try:
        file_id = _upload_to_drive(service, tmp_path, content_type, safe_name, folder_id)
    finally:
        try:
            os.remove(tmp_path)
        except OSError as exc:
            logger.warning("No se pudo eliminar archivo temporal %s: %s", tmp_path, exc)

    try:
        _set_public_permission(service, file_id)
    except Exception:
        logger.error("Fallo al asignar permisos públicos, eliminando archivo huérfano %s", file_id)
        try:
            delete_file(file_id)
        except Exception:
            logger.warning("No se pudo eliminar archivo huérfano %s", file_id)
        raise

    logger.info("Archivo subido a Drive: %s (%s) file_id=%s", safe_name, content_type, file_id)
    return {"url": f"https://drive.google.com/uc?id={file_id}&export=view", "file_id": file_id}


def upload_image_bytes(file_bytes, filename, product_id, mime_type="image/jpeg"):
    """Upload an image to Google Drive under rassa/productos/{product_id}/.

    Returns (url, file_id). The file is uploaded as PRIVATE — call
    make_public() separately after confirming the DB transaction.
    """
    if not isinstance(product_id, int):
        raise ValueError("product_id must be an integer")

    # Validate magic bytes
    byte_io = io.BytesIO(file_bytes)
    if not _validate_magic_bytes(byte_io, mime_type):
        raise ValueError(
            f"El contenido del archivo no coincide con el tipo {mime_type}. "
            "Asegurate de que el archivo no esté corrupto."
        )

    # Validate file size
    file_size_mb = len(file_bytes) / MB
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE_MB}MB.")

    # Sanitize filename
    filename = _sanitize_filename(filename)

    service = _get_drive_service()
    folder_id = config("GOOGLE_DRIVE_FOLDER_ID", default=None) or getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)

    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID not configured.")

    parent_folder_id = _get_or_create_folder(service, "productos", folder_id)
    product_folder_id = _get_or_create_folder(service, str(product_id), parent_folder_id)

    file_metadata = {
        "name": filename,
        "parents": [product_folder_id],
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)

    file = _execute_with_retry(service.files().create, body=file_metadata, media_body=media, fields="id")

    file_id = file.get("id")
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    logger.info("Image uploaded to Drive (private): %s -> %s", filename, file_id)
    return url, file_id


def make_public(file_id):
    """Make a Drive file readable by anyone with the link.

    Returns True on success, False on failure.
    """
    if not file_id:
        return True
    try:
        service = _get_drive_service()
        permission = {"type": "anyone", "role": "reader"}
        _execute_with_retry(service.permissions().create, fileId=file_id, body=permission)
        logger.info("Image made public on Drive: %s", file_id)
        return True
    except Exception:
        logger.warning("Failed to make image public on Drive: %s", file_id, exc_info=True)
        return False


def delete_file(file_id):
    """Elimina un archivo de Google Drive por su ID.

    Args:
        file_id (str): ID del archivo en Google Drive.

    Raises:
        ValueError: Si file_id está vacío.
        Exception: Si la eliminación falla después de los reintentos.
    """
    if not file_id:
        raise ValueError("file_id es requerido para eliminar un archivo.")

    service = _get_drive_service()
    try:
        _execute_with_retry(service.files().delete, fileId=file_id)
        logger.info("Archivo eliminado de Drive: %s", file_id)
    except Exception as exc:
        logger.error("Error al eliminar archivo %s de Drive: %s", file_id, exc)
        raise


def delete_image(file_id):
    """Delete a file from Google Drive by its ID.

    Returns True on success or if file_id is empty, False on failure.
    """
    if not file_id:
        return True
    try:
        service = _get_drive_service()
        _execute_with_retry(service.files().delete, fileId=file_id)
        logger.info("Image deleted from Drive: %s", file_id)
        return True
    except Exception:
        logger.warning("Failed to delete image from Drive: %s", file_id, exc_info=True)
        return False
