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
        self.private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "")
        self.url_endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "").rstrip("/")

    @property
    def _auth(self):
        return (self.private_key, "")

    def _save(self, name, content):
        """Upload the file and return its stored path (ImageKit `name`)."""
        data = {"fileName": name, "useUniqueFileName": "false"}
        content_type = getattr(content, "content_type", None)
        files = {"file": (name, content, content_type)}
        response = requests.post(
            UPLOAD_ENDPOINT, data=data, files=files, auth=self._auth, timeout=60
        )
        response.raise_for_status()
        stored_name = response.json().get("name") or name
        logger.info("ImageKit upload: %s", stored_name)
        return stored_name

    def url(self, name):
        # CDN URL; transformations can be appended as ?tr=... by callers.
        return f"{self.url_endpoint}/{quote(name)}"

    def _find(self, name):
        """Return the fileId for `name`, or None if not found."""
        response = requests.get(
            FILES_ENDPOINT, params={"name": name}, auth=self._auth, timeout=30
        )
        if response.status_code != 200:
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
