"""Google Drive service for uploading and managing product images."""

import io
import logging

from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

MIME_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _get_credentials():
    """Build credentials from env vars or credentials file."""
    credentials_path = getattr(settings, "GOOGLE_DRIVE_CREDENTIALS_PATH", None)
    refresh_token = getattr(settings, "GOOGLE_DRIVE_REFRESH_TOKEN", None)
    client_id = getattr(settings, "GOOGLE_DRIVE_CLIENT_ID", None)
    client_secret = getattr(settings, "GOOGLE_DRIVE_CLIENT_SECRET", None)

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
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as FileCredentials

        creds = FileCredentials.from_authorized_user_file(credentials_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    raise ValueError(
        "Google Drive credentials not configured. "
        "Set GOOGLE_DRIVE_REFRESH_TOKEN, GOOGLE_DRIVE_CLIENT_ID, "
        "and GOOGLE_DRIVE_CLIENT_SECRET in environment."
    )


def get_drive_service():
    """Return an authorized Google Drive API service instance."""
    import httplib2

    creds = _get_credentials()
    http = httplib2.Http(timeout=30)
    creds.refresh(httplib2.Request())
    return build("drive", "v3", credentials=creds, http=http)


def upload_image(file_bytes, filename, product_id, mime_type="image/jpeg"):
    """Upload an image to Google Drive under rassa/productos/{product_id}/.

    Returns the publicly accessible URL of the uploaded file.
    """
    service = get_drive_service()
    folder_id = getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)

    if not folder_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID not configured.")

    parent_folder_id = _get_or_create_folder(service, "productos", folder_id)
    product_folder_id = _get_or_create_folder(service, str(product_id), parent_folder_id)

    file_metadata = {
        "name": filename,
        "parents": [product_folder_id],
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)

    file = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
        )
        .execute()
    )

    file_id = file.get("id")
    _set_public_permission(service, file_id)

    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    logger.info("Image uploaded to Drive: %s → %s", filename, file_id)
    return url, file_id


def delete_image(file_id):
    """Delete a file from Google Drive by its ID."""
    if not file_id:
        return
    try:
        service = get_drive_service()
        service.files().delete(fileId=file_id).execute()
        logger.info("Image deleted from Drive: %s", file_id)
    except Exception:
        logger.warning("Failed to delete image from Drive: %s", file_id, exc_info=True)


def _get_or_create_folder(service, name, parent_id):
    """Find or create a folder by name inside parent_id. Returns folder ID."""
    safe_name = name.replace("'", "\\'")
    query = (
        f"mimeType='application/vnd.google-apps.folder'"
        f" and name='{safe_name}'"
        f" and '{parent_id}' in parents"
        f" and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)", spaces="drive").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    folder_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]


def _set_public_permission(service, file_id):
    """Make a file readable by anyone with the link. Raises on failure."""
    permission = {"type": "anyone", "role": "reader"}
    service.permissions().create(fileId=file_id, body=permission).execute()
