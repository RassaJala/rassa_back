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
"""

import logging
import os
import re
import tempfile
import time

from decouple import config
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .drive_config import (
    MAGIC_BYTES,
    MAX_FILE_SIZE_MB,
    MAX_FILENAME_LENGTH,
    MAX_RETRIES,
    MIME_TYPES,
    RETRY_BACKOFF_BASE,
    RETRYABLE_STATUS_CODES,
    SCOPES,
)

logger = logging.getLogger(__name__)


def _get_credentials():
    """Construye credenciales OAuth2 desde variables de entorno.

    Returns:
        Credentials: Credenciales OAuth2 válidas.

    Raises:
        ValueError: Si faltan variables de entorno requeridas.
    """
    client_id = config("GOOGLE_DRIVE_CLIENT_ID", default="")
    client_secret = config("GOOGLE_DRIVE_CLIENT_SECRET", default="")
    refresh_token = config("GOOGLE_DRIVE_REFRESH_TOKEN", default="")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Faltan variables de entorno para Google Drive OAuth2: "
            "GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, "
            "GOOGLE_DRIVE_REFRESH_TOKEN"
        )

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )


def _get_drive_service():
    """Construye y retorna un servicio de Google Drive autenticado.

    Refresca el token de acceso antes de retornar el servicio.

    Returns:
        Resource: Servicio de Google Drive autenticado.

    Raises:
        Exception: Si la autenticación falla.
    """
    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request

        credentials.refresh(Request())
        return build("drive", "v3", credentials=credentials)
    except Exception as exc:
        logger.error("Error al autenticar con Google Drive: %s", exc)
        raise


def _sanitize_filename(name):
    """Sanitiza el nombre del archivo para prevenir inyección y paths maliciosos.

    Aplica las siguientes transformaciones:
    - Extrae solo el nombre base (sin directorios)
    - Remueve caracteres de control
    - Reemplaza caracteres peligrosos por guiones bajos
    - Limita la longitud a MAX_FILENAME_LENGTH
    - Rechaza nombres que empiezan con punto

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

    Previene suplantación de tipo de contenido donde un atacante envía
    Content-Type: image/jpeg para un archivo HTML/JS.

    Args:
        file: Archivo con método seek() y read().
        expected_type (str): Tipo MIME esperado (ej: 'image/jpeg').

    Returns:
        bool: True si los magic bytes coinciden, False si no.
    """
    file.seek(0)
    header = file.read(16)
    file.seek(0)

    magic = MAGIC_BYTES.get(expected_type)
    if magic is None:
        return False

    if expected_type == "image/webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"

    return header[: len(magic)] == magic


def _execute_with_retry(func, *args, **kwargs):
    """Ejecuta una función de la API de Drive con reintento y exponential backoff.

    Reintenta automáticamente en errores temporales (429, 500, 502, 503, timeout).
    Usa exponential backoff con base RETRY_BACKOFF_BASE.

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
            status = getattr(exc, "resp", None)
            status_code = getattr(status, "status", None) if status else None
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
        folder_id = config("GOOGLE_DRIVE_FOLDER_ID", default="")
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID no está configurado.")

    safe_name = _sanitize_filename(filename)

    content_type = file.content_type
    if content_type not in MIME_TYPES:
        raise ValueError(
            f"Tipo de archivo no permitido: {content_type}. "
            f"Formatos válidos: {', '.join(MIME_TYPES.keys())}"
        )

    if not _validate_magic_bytes(file, content_type):
        raise ValueError(
            f"El contenido del archivo no coincide con el tipo {content_type}. "
            "Asegurate de que el archivo no esté corrupto."
        )

    file.seek(0, os.SEEK_END)
    file_size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE_MB}MB.")

    service = _get_drive_service()

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(safe_name)[1]) as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
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
    finally:
        try:
            os.remove(tmp_path)
        except OSError as exc:
            logger.warning("No se pudo eliminar archivo temporal %s: %s", tmp_path, exc)

    file_id = uploaded.get("id")

    # Visibilidad pública (W3): las imágenes se hacen públicas automáticamente
    # para que los clientes puedan verlas desde el frontend.
    # Ver docstring del módulo para el análisis completo de esta decisión.
    _execute_with_retry(
        service.permissions().create,
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    )

    url = f"https://drive.google.com/uc?id={file_id}&export=download"
    logger.info("Archivo subido a Drive: %s (%s) → %s", safe_name, content_type, url)
    return {"url": url, "file_id": file_id}


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
