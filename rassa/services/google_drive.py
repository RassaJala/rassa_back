"""Servicio para subir archivos a Google Drive usando OAuth2.

Requiere credenciales OAuth2 (Client ID + Client Secret) y un refresh token
obtenido mediante autorización del usuario.

Pasos para configurar:
1. Crear credenciales OAuth2 en Google Cloud Console
2. Ejecutar: python manage.py authorize_drive
3. Seguir las instrucciones para autorizar la app
4. El refresh token se guarda automáticamente en .env
"""

import logging
import os
import tempfile

from decouple import config
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Tipos MIME permitidos
MIME_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
}

MAX_FILE_SIZE_MB = 10


def _get_credentials():
    """Construye credenciales OAuth2 desde variables de entorno."""
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
    """Construye y retorna un servicio de Google Drive autenticado."""
    credentials = _get_credentials()
    # Refrescar el token
    from google.auth.transport.requests import Request

    credentials.refresh(Request())
    return build("drive", "v3", credentials=credentials)


def upload_image(file, filename):
    """Sube una imagen a Google Drive y retorna la URL pública de descarga.

    Args:
        file: Archivo subido (request.FILES['archivo']).
        filename: Nombre del archivo (ej: 'tomate.jpg').

    Returns:
        str: URL de descarga del archivo en Drive.

    Raises:
        ValueError: Si el archivo no es válido o excede el tamaño máximo.
    """
    folder_id = config("GOOGLE_DRIVE_FOLDER_ID", default="")
    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID no está configurado.")

    # Validar tipo MIME
    content_type = file.content_type
    if content_type not in MIME_TYPES:
        raise ValueError(
            f"Tipo de archivo no permitido: {content_type}. Formatos válidos: {', '.join(MIME_TYPES.keys())}"
        )

    # Validar tamaño
    file.seek(0, os.SEEK_END)
    file_size_mb = file.tell() / (1024 * 1024)
    file.seek(0)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE_MB}MB.")

    service = _get_drive_service()

    # MediaFileUpload necesita un path en disco, no un InMemoryUploadedFile
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        media = MediaFileUpload(tmp_path, mimetype=content_type, resumable=True)

        uploaded = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    file_id = uploaded.get("id")

    # Hacer el archivo accesible públicamente
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Construir URL de descarga directa
    url = f"https://drive.google.com/uc?id={file_id}&export=download"
    logger.info("Archivo subido a Drive: %s → %s", filename, url)
    return url
