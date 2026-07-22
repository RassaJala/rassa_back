"""Google Drive service for uploading and managing product images."""

import io
import logging
import time

from django.conf import settings
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

MIME_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

DRIVE_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]

_service_cache = {"service": None}


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
    """Return a cached, authorized Google Drive API service instance."""
    if _service_cache["service"] is not None:
        return _service_cache["service"]

    import httplib2

    creds = _get_credentials()
    http = httplib2.Http(timeout=DRIVE_TIMEOUT)
    creds.refresh(httplib2.Request())
    service = build("drive", "v3", credentials=creds, http=http)
    _service_cache["service"] = service
    return service


def _drive_retry(request):
    """Execute a Drive API request with retry and exponential backoff.

    Retries on transient HTTP errors (429, 500, 502, 503, 504).
    """
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(
                    "Drive API error %d (attempt %d/%d), retrying in %ds",
                    status,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                last_exc = exc
            else:
                raise
    raise last_exc


def upload_image(file_bytes, filename, product_id, mime_type="image/jpeg"):
    """Upload an image to Google Drive under rassa/productos/{product_id}/.

    Returns (url, file_id). The file is uploaded as PRIVATE — call
    make_public() separately after confirming the DB transaction.
    """
    if not isinstance(product_id, int):
        raise ValueError("product_id must be an integer")

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

    file = _drive_retry(service.files().create(body=file_metadata, media_body=media, fields="id"))

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
        service = get_drive_service()
        permission = {"type": "anyone", "role": "reader"}
        _drive_retry(service.permissions().create(fileId=file_id, body=permission))
        logger.info("Image made public on Drive: %s", file_id)
        return True
    except Exception:
        logger.warning("Failed to make image public on Drive: %s", file_id, exc_info=True)
        return False


def delete_image(file_id):
    """Delete a file from Google Drive by its ID.

    Returns True on success or if file_id is empty, False on failure.
    """
    if not file_id:
        return True
    try:
        service = get_drive_service()
        _drive_retry(service.files().delete(fileId=file_id))
        logger.info("Image deleted from Drive: %s", file_id)
        return True
    except Exception:
        logger.warning("Failed to delete image from Drive: %s", file_id, exc_info=True)
        return False


def _get_or_create_folder(service, name, parent_id):
    """Find or create a folder by name inside parent_id. Returns folder ID."""
    if not isinstance(parent_id, str) or not parent_id.strip():
        raise ValueError("parent_id must be a non-empty string")

    safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"mimeType='application/vnd.google-apps.folder'"
        f" and name='{safe_name}'"
        f" and '{parent_id}' in parents"
        f" and trashed=false"
    )
    results = _drive_retry(service.files().list(q=query, fields="files(id)", spaces="drive"))
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    folder_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = _drive_retry(service.files().create(body=folder_metadata, fields="id"))
    return folder["id"]
