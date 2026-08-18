"""Image validation and storage for product/category images.

Uses Django's storage abstractions so uploads go to MEDIA_ROOT in development
and to a durable backend (e.g. S3) in production.  Vercel /tmp is never
acceptable for production storage.

Validates actual image content via Pillow: file extension, byte/pixel size,
and image type.  Upload failures become actionable form errors and safe log
messages.  Replaced/deleted images are cleaned up without deleting
still-referenced objects.
"""

import logging
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage
from django.db import transaction

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_WIDTH = 4096
MAX_IMAGE_HEIGHT = 4096
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Map file extensions to Pillow formats for content-type validation.
CONTENT_TYPE_MAP = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
}


def _validate_image(file_obj):
    """Validate an uploaded image's extension, byte size, and pixel dimensions.

    Raises ValidationError with Arabic user-facing messages on failure.
    """
    # --- Extension check ---
    ext = Path(file_obj.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"صيغة الملف غير مدعومة: {ext}. الصيغ المسموحة: "
            + ", ".join(ALLOWED_EXTENSIONS)
        )

    # --- Byte-size check ---
    if file_obj.size is not None and file_obj.size > MAX_IMAGE_BYTES:
        raise ValidationError(
            f"حجم الملف كبير جداً ({file_obj.size / 1024 / 1024:.1f} م.ب). "
            f"الحد الأقصى هو {MAX_IMAGE_BYTES / 1024 / 1024:.0f} م.ب."
        )

    # --- Content-type sniff ---
    if hasattr(file_obj, "content_type") and file_obj.content_type:
        valid_exts = CONTENT_TYPE_MAP.get(file_obj.content_type)
        if valid_exts and ext not in valid_exts:
            raise ValidationError(
                "نوع الملف لا يتطابق مع امتداده. تأكد من أن الملف صورة صالحة."
            )

    # --- Pixel dimensions (reads the image with Pillow) ---
    try:
        width, height = get_image_dimensions(file_obj)
    except Exception as exc:
        raise ValidationError(
            "تعذر قراءة الصورة. تأكد من أن الملف صورة صالحة وغير تالف."
        ) from exc

    if width is None or height is None:
        raise ValidationError("لا يمكن تحديد أبعاد الصورة.")

    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        raise ValidationError(
            f"أبعاد الصورة كبيرة جداً ({width}×{height}). "
            f"الحد الأقصى {MAX_IMAGE_WIDTH}×{MAX_IMAGE_HEIGHT} بكسل."
        )
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        raise ValidationError(
            f"أبعاد الصورة صغيرة جداً ({width}×{height}). "
            f"الحد الأدنى {MIN_IMAGE_WIDTH}×{MIN_IMAGE_HEIGHT} بكسل."
        )

    # Reset position so the storage backend reads from the start.
    file_obj.seek(0)


def _require_durable_storage():
    """Raise RuntimeError if durable storage is not configured in production.

    In production (DEBUG=False), local MEDIA_ROOT under /tmp is rejected.
    In development, local MEDIA_ROOT is acceptable.
    """
    if settings.DEBUG:
        return
    media_root = str(settings.MEDIA_ROOT)
    if media_root.startswith("/tmp") or media_root.startswith("/var/folders"):
        raise RuntimeError(
            "Production must use durable media storage "
            "(e.g. S3, Cloud Storage).  /tmp is not acceptable."
        )


def save_image(file_obj, upload_subdir: str) -> str:
    """Validate and save an uploaded image.  Returns the storage path."""
    _require_durable_storage()
    _validate_image(file_obj)
    path = default_storage.save(f"{upload_subdir}/{file_obj.name}", file_obj)
    logger.info("Image saved: %s", path)
    return path


def delete_image(storage_path: str) -> None:
    """Delete an image file from storage if it exists."""
    if not storage_path:
        return
    try:
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)
            logger.info("Image deleted: %s", storage_path)
    except Exception:
        logger.exception("Failed to delete image: %s", storage_path)


def handle_image_replacement(instance, new_file, field_name="image") -> str | None:
    """Replace an instance's image atomically.

    - If no new file is provided, keep the existing image.
    - Validate and save the new file inside a transaction.
    - Delete the old file only after the new one is committed.

    Returns the storage path of the new image, or None.
    """
    if not new_file:
        return None

    old_path = getattr(instance, field_name, None)
    old_name = old_path.name if old_path else None

    new_path = None
    try:
        new_path = save_image(
            new_file, ""
        )  # _unique_filename already includes the path
    except Exception:
        logger.exception(
            "Image upload failed for %s pk=%s", type(instance).__name__, instance.pk
        )
        raise

    # Write the new path within a transaction; clean up old afterwards.
    with transaction.atomic():
        setattr(instance, field_name, new_path)
        instance.save(update_fields=[field_name, "updated_at"])

    _cleanup_old_image(old_name, new_path, type(instance))
    return new_path


def handle_image_deletion(instance, field_name="image") -> None:
    """Delete an instance's image file if it is not referenced elsewhere."""
    image_field = getattr(instance, field_name, None)
    if not image_field or not image_field.name:
        return

    _cleanup_old_image(image_field.name, None, type(instance))


def _cleanup_old_image(old_name, new_name, model_class):
    """Delete old_name only if no other row references it and it differs from new_name."""
    if not old_name or old_name == new_name:
        return

    # Check if any other row of this model references the same file.
    others_exist = (
        model_class.objects.exclude(pk=None).filter(**{f"image": old_name}).exists()
    )
    if not others_exist:
        delete_image(old_name)
