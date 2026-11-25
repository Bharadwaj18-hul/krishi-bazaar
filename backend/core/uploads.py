"""Krishi Bazaar — safe product-photo uploads."""
import secrets
from typing import Optional

from fastapi import UploadFile

from . import config
from ..services.orders import BusinessError

UPLOAD_PREFIX = "products/up_"  # uploaded photos; the demo photos (products/<name>.jpg) are never deleted


def _detect_extension(head: bytes) -> Optional[str]:
    """Identify the real image type from its first bytes (never trust the filename)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def save_product_image(upload: Optional[UploadFile]) -> Optional[str]:
    """Store an uploaded photo; returns the path relative to /media, or None if nothing was uploaded."""
    if upload is None or not upload.filename:
        return None
    data = upload.file.read(config.MAX_UPLOAD_BYTES + 1)
    if not data:
        return None
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise BusinessError(f"Photo is too large (max {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    ext = _detect_extension(data[:16])
    if not ext:
        raise BusinessError("Photo must be a JPG, PNG or WEBP image.")
    name = f"{UPLOAD_PREFIX}{secrets.token_hex(8)}.{ext}"
    target = config.MEDIA_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return name


def delete_uploaded_image(relative_path: Optional[str]) -> None:
    """Remove an earlier *uploaded* photo (demo/seed photos are left alone)."""
    if relative_path and relative_path.startswith(UPLOAD_PREFIX):
        try:
            (config.MEDIA_DIR / relative_path).unlink(missing_ok=True)
        except OSError:
            pass
