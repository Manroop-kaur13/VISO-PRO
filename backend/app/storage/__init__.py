"""Provider-neutral private storage facade.

New uploads use the configured provider. Persisted keys are provider tagged so
Cloudinary and pre-existing S3 captures can coexist during migration/rollback.
"""

from app.config import get_settings
from app.storage import cloudinary_storage, s3


class StorageError(RuntimeError):
    """A storage provider operation failed."""


def storage_is_configured() -> bool:
    provider = get_settings().storage_provider.lower()
    if provider == "cloudinary":
        return cloudinary_storage.storage_is_configured()
    if provider == "s3":
        return s3.storage_is_configured()
    return False


def storage_is_ready() -> bool:
    """Check actual remote reachability, not only the presence of credentials."""
    provider = get_settings().storage_provider.lower()
    if provider == "cloudinary":
        return cloudinary_storage.storage_is_ready()
    if provider == "s3":
        return s3.storage_is_ready()
    return False


def put_object(key: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return the opaque provider locator to persist in SQL."""
    provider = get_settings().storage_provider.lower()
    try:
        if provider == "cloudinary":
            return cloudinary_storage.put_object(key, data, content_type)
        if provider == "s3":
            s3.put_object(key, data, content_type)
            return key
    except Exception as exc:
        raise StorageError("Image storage upload failed.") from exc
    raise StorageError("The configured image storage provider is unsupported.")


def _provider_for_key(key: str) -> str:
    # Older database rows store plain S3 object keys. Cloudinary locators are
    # self-describing and continue to work even if the upload provider changes.
    return "cloudinary" if key.startswith("cloudinary:") else "s3"


def signed_download_url(key: str, *, as_attachment: bool = False) -> str:
    try:
        if _provider_for_key(key) == "cloudinary":
            return cloudinary_storage.signed_download_url(key, as_attachment=as_attachment)
        return s3.signed_download_url(key, as_attachment=as_attachment)
    except Exception as exc:
        raise StorageError("Image storage download URL could not be created.") from exc


def delete_object(key: str) -> None:
    try:
        if _provider_for_key(key) == "cloudinary":
            cloudinary_storage.delete_object(key)
        else:
            s3.delete_object(key)
    except Exception as exc:
        raise StorageError("Image storage deletion failed.") from exc
