"""Cloudinary adapter using authenticated delivery for every new asset."""

import json
import mimetypes
import time
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

import cloudinary
from cloudinary import api, uploader, utils

from app.config import get_settings

SIGNED_URL_TTL_SECONDS = 300


def storage_is_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    )


def _configure() -> None:
    settings = get_settings()
    if not storage_is_configured():
        raise RuntimeError("Cloudinary credentials are not configured.")
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret.get_secret_value(),
        secure=True,
    )


def storage_is_ready() -> bool:
    """Ping Cloudinary so readiness reflects connectivity as well as config."""
    if not storage_is_configured():
        return False
    try:
        _configure()
        return api.ping().get("status") == "ok"
    except Exception:
        return False


def _decode_locator(locator: str) -> dict[str, str]:
    if not locator.startswith("cloudinary:"):
        raise ValueError("Not a Cloudinary storage locator.")
    result = json.loads(locator[len("cloudinary:") :])
    required = {"asset_id", "public_id", "resource_type", "format"}
    if not required.issubset(result):
        raise ValueError("Cloudinary storage locator is incomplete.")
    return result


def put_object(key: str, data: bytes, content_type: str) -> str:
    """Upload an image/video as authenticated and return its persisted locator."""
    _configure()
    resource_type = "video" if content_type.startswith("video/") else "image"
    public_id = str(PurePosixPath(key).with_suffix(""))
    result: dict[str, Any] = uploader.upload(
        BytesIO(data),
        public_id=public_id,
        resource_type=resource_type,
        type="authenticated",
        overwrite=False,
        unique_filename=False,
        use_filename=False,
        # Do not apply transformations to clinical source media.
        tags=["viso-pro"],
    )
    actual_public_id = str(result["public_id"])
    asset_id = str(result["asset_id"])
    actual_resource_type = str(result.get("resource_type", resource_type))
    actual_format = str(result.get("format") or mimetypes.guess_extension(content_type) or "")
    actual_format = actual_format.lstrip(".")
    if actual_resource_type not in {"image", "video"} or not actual_format:
        # Fail closed: do not persist an asset that cannot be securely served.
        uploader.destroy(
            actual_public_id,
            resource_type=actual_resource_type,
            type="authenticated",
            invalidate=True,
        )
        raise RuntimeError("Cloudinary returned incomplete asset metadata.")
    locator = {
        "asset_id": asset_id,
        "public_id": actual_public_id,
        "resource_type": actual_resource_type,
        "format": actual_format,
    }
    return "cloudinary:" + json.dumps(locator, separators=(",", ":"))


def signed_download_url(locator: str, *, as_attachment: bool = False) -> str:
    """Return a five-minute signed URL for an authenticated asset."""
    _configure()
    asset = _decode_locator(locator)
    options: dict[str, Any] = {
        "type": "authenticated",
        "resource_type": asset["resource_type"],
        "expires_at": int(time.time()) + SIGNED_URL_TTL_SECONDS,
        "attachment": as_attachment,
        "secure": True,
    }
    return str(utils.private_download_url(asset["public_id"], asset["format"], **options))


def delete_object(locator: str) -> None:
    """Delete the authenticated Cloudinary asset referenced by its locator."""
    _configure()
    asset = _decode_locator(locator)
    result = uploader.destroy(
        asset["public_id"],
        resource_type=asset["resource_type"],
        type="authenticated",
        invalidate=True,
    )
    if result.get("result") not in {"ok", "not found"}:
        raise RuntimeError("Cloudinary did not confirm asset deletion.")
