"""ImageKit media-library storage backend.

Replaces the Supabase/S3 backend: product and category images are uploaded to
ImageKit's media library and served from its CDN (which also supports on-the-
fly transformations via `?tr=` query params).

Design notes
------------
- The model's ImageField stores the ImageKit *path* (e.g. "products/<uuid>.jpg").
- Uploads use `useUniqueFileName=false` so the stored name is exactly the name
  Django generated - that keeps `url()` deterministic.
- ImageKit's delete API needs a `fileId`, so `delete()`/`exists()` first look
  the file up by name through the list-files endpoint.
- Uses plain `requests` (already a project dependency) instead of the
  imagekitio SDK to avoid an extra dependency; Basic auth user = private key.
"""

import logging
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.files.storage import Storage

logger = logging.getLogger(__name__)

UPLOAD_ENDPOINT = "https://upload.imagekit.io/api/v1/files/upload"
FILES_ENDPOINT = "https://api.imagekit.io/v1/files"


class ImageKitStorage(Storage):
    """Django storage backend backed by ImageKit's media library."""

    def __init__(self):
        # Private key only: ImageKit authenticates server-side calls with
        # Basic auth where the username is the private key and password is "".
        self.private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "").strip()
        self.url_endpoint = (
            getattr(settings, "IMAGEKIT_URL_ENDPOINT", "").strip().rstrip("/")
        )

    @property
    def _auth(self):
        return (self.private_key, "")

    @staticmethod
    def _split_name(name):
        """Split a Django storage path into ImageKit ``(folder, fileName)``."""
        normalized = name.replace("\\", "/").lstrip("/")
        if "/" in normalized:
            folder_part, filename = normalized.rsplit("/", 1)
            return f"/{folder_part}", filename
        return "", normalized

    def _log_error_response(self, action, name, response):
        """Log sanitized non-secret HTTP status and body details on failure."""
        body = (response.text or "")[:500]
        if self.private_key:
            body = body.replace(self.private_key, "[REDACTED]")
        logger.error(
            "ImageKit %s failed: status=%s path=%s body=%s",
            action,
            response.status_code,
            name,
            body,
        )

    def _save(self, name, content):
        """Upload the file and return its deterministic stored path."""
        folder, filename = self._split_name(name)
        data = {"fileName": filename, "useUniqueFileName": "false"}
        if folder:
            data["folder"] = folder
        content_type = getattr(content, "content_type", None)
        files = {"file": (filename, content, content_type)}
        response = requests.post(
            UPLOAD_ENDPOINT, data=data, files=files, auth=self._auth, timeout=60
        )
        if response.status_code >= 400:
            self._log_error_response("upload", name, response)
        response.raise_for_status()

        payload = response.json()
        file_path = payload.get("filePath")
        if file_path:
            stored_name = file_path.lstrip("/")
        else:
            returned_name = payload.get("name")
            if returned_name and folder and "/" not in returned_name:
                stored_name = f"{folder.lstrip('/')}/{returned_name}"
            else:
                stored_name = (returned_name or name).lstrip("/")

        logger.info("ImageKit upload: %s", stored_name)
        return stored_name

    def url(self, name):
        # CDN URL; transformations can be appended as ?tr=... by callers.
        clean_name = name.replace("\\", "/").lstrip("/")
        return f"{self.url_endpoint}/{quote(clean_name, safe='/')}"

    def _find(self, name):
        """Return the fileId for `name`, or None if not found."""
        folder, filename = self._split_name(name)
        params = {"name": filename}
        if folder:
            params["path"] = folder
        response = requests.get(
            FILES_ENDPOINT, params=params, auth=self._auth, timeout=30
        )
        if response.status_code != 200:
            self._log_error_response("find", name, response)
            return None
        items = response.json()
        if not items:
            return None
        return items[0].get("fileId")

    def exists(self, name):
        return self._find(name) is not None

    def delete(self, name):
        file_id = self._find(name)
        if not file_id:
            return
        response = requests.delete(
            f"{FILES_ENDPOINT}/{file_id}", auth=self._auth, timeout=30
        )
        if response.status_code >= 400:
            self._log_error_response("delete", name, response)
        response.raise_for_status()
        logger.info("ImageKit delete: %s", name)

    def get_available_name(self, name, max_length=None):
        # Names come from _unique_filename (uuid4 hex) - collisions are
        # practically impossible, so skip the default exists() lookup.
        return name

    def size(self, name):
        # Not used by this project.
        raise NotImplementedError("ImageKitStorage does not provide size()")

    def open(self, name, mode="rb"):
        # Not used by this project (uploads are admin-driven, never read back).
        raise NotImplementedError("ImageKitStorage does not provide open()")
