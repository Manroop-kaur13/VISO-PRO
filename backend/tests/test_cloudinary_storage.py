from __future__ import annotations

import json

import pytest

from app.config import Settings, get_settings
from app import storage
from app.storage import cloudinary_storage


@pytest.fixture(autouse=True)
def clear_cached_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure_env(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "synthetic-cloud")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "synthetic-key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "synthetic-secret")
    get_settings.cache_clear()


def test_cloudinary_upload_signed_retrieval_and_delete_are_authenticated(monkeypatch) -> None:
    _configure_env(monkeypatch)
    calls: dict[str, object] = {}
    monkeypatch.setattr(cloudinary_storage.cloudinary, "config", lambda **kwargs: calls.update(config=kwargs))

    def upload(file, **options):
        calls["upload"] = options
        return {
            "asset_id": "synthetic-asset-id",
            "public_id": options["public_id"],
            "resource_type": options["resource_type"],
            "format": "png",
        }

    monkeypatch.setattr(cloudinary_storage.uploader, "upload", upload)
    locator = cloudinary_storage.put_object(
        "records/synthetic-session/synthetic-capture.png",
        b"synthetic image bytes",
        "image/png",
    )
    record = json.loads(locator.removeprefix("cloudinary:"))
    assert record["asset_id"] == "synthetic-asset-id"
    assert record["public_id"] == "records/synthetic-session/synthetic-capture"
    assert calls["upload"]["type"] == "authenticated"
    assert calls["upload"]["resource_type"] == "image"

    monkeypatch.setattr(
        cloudinary_storage.utils,
        "private_download_url",
        lambda public_id, fmt, **options: calls.update(download=(public_id, fmt, options)) or "https://signed.invalid/temp",
    )
    assert cloudinary_storage.signed_download_url(locator) == "https://signed.invalid/temp"
    public_id, fmt, options = calls["download"]
    assert public_id == record["public_id"]
    assert fmt == "png"
    assert options["type"] == "authenticated"
    assert options["expires_at"] > 0

    monkeypatch.setattr(
        cloudinary_storage.uploader,
        "destroy",
        lambda public_id, **options: calls.update(delete=(public_id, options)) or {"result": "ok"},
    )
    cloudinary_storage.delete_object(locator)
    delete_public_id, delete_options = calls["delete"]
    assert delete_public_id == record["public_id"]
    assert delete_options["type"] == "authenticated"
    assert delete_options["resource_type"] == "image"


def test_cloudinary_video_upload_uses_video_resource_type(monkeypatch) -> None:
    _configure_env(monkeypatch)
    calls: dict[str, object] = {}
    monkeypatch.setattr(cloudinary_storage.cloudinary, "config", lambda **kwargs: None)

    def upload(file, **options):
        calls.update(options)
        return {
            "asset_id": "synthetic-video-id",
            "public_id": options["public_id"],
            "resource_type": options["resource_type"],
            "format": "webm",
        }

    monkeypatch.setattr(cloudinary_storage.uploader, "upload", upload)
    locator = cloudinary_storage.put_object(
        "records/synthetic-session/synthetic-capture.webm",
        b"synthetic video bytes",
        "video/webm",
    )
    assert calls["resource_type"] == "video"
    assert calls["type"] == "authenticated"
    assert json.loads(locator.removeprefix("cloudinary:"))["resource_type"] == "video"


def test_cloudinary_readiness_requires_a_successful_remote_ping(monkeypatch) -> None:
    _configure_env(monkeypatch)
    monkeypatch.setattr(cloudinary_storage.cloudinary, "config", lambda **kwargs: None)
    monkeypatch.setattr(cloudinary_storage.api, "ping", lambda: {"status": "ok"})
    assert cloudinary_storage.storage_is_configured()
    assert cloudinary_storage.storage_is_ready()
    monkeypatch.setattr(cloudinary_storage.api, "ping", lambda: {"status": "error"})
    assert not cloudinary_storage.storage_is_ready()


def test_existing_s3_keys_remain_readable_when_cloudinary_is_selected(monkeypatch) -> None:
    monkeypatch.setattr(storage, "get_settings", lambda: Settings(storage_provider="cloudinary"))
    monkeypatch.setattr(storage.s3, "signed_download_url", lambda key, as_attachment=False: f"https://s3.invalid/{key}")
    monkeypatch.setattr(
        cloudinary_storage,
        "signed_download_url",
        lambda key, as_attachment=False: "https://cloudinary.invalid/signed",
    )

    assert storage.signed_download_url("records/old-s3-object.jpg").startswith("https://s3.invalid/")
    assert storage.signed_download_url("cloudinary:{\"asset_id\":\"a\"}") == "https://cloudinary.invalid/signed"
