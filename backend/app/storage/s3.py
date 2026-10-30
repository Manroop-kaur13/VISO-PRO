"""Private S3-compatible object storage for imaging uploads."""

from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings


@lru_cache(maxsize=1)
def _client():
    settings = get_settings()
    kwargs = {"region_name": settings.s3_region}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.s3_access_key_id:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
    if settings.s3_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key.get_secret_value()
    if settings.s3_session_token:
        kwargs["aws_session_token"] = settings.s3_session_token.get_secret_value()
    return boto3.client("s3", **kwargs)


def storage_is_configured() -> bool:
    return bool(get_settings().s3_bucket)


def storage_is_ready() -> bool:
    bucket = get_settings().s3_bucket
    if not bucket:
        return False
    try:
        _client().head_bucket(Bucket=bucket)
    except (BotoCoreError, ClientError):
        return False
    return True


def put_object(key: str, data: bytes, content_type: str) -> None:
    bucket = get_settings().s3_bucket
    if not bucket:
        raise RuntimeError("Object storage is not configured.")
    _client().put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        Metadata={"service": "viso-pro"},
    )


def delete_object(key: str) -> None:
    bucket = get_settings().s3_bucket
    if bucket:
        _client().delete_object(Bucket=bucket, Key=key)


def signed_download_url(key: str, *, as_attachment: bool = False) -> str:
    settings = get_settings()
    if not settings.s3_bucket:
        raise RuntimeError("Object storage is not configured.")
    params = {"Bucket": settings.s3_bucket, "Key": key}
    if as_attachment:
        extension = key.rsplit(".", 1)[-1].lower()
        params["ResponseContentDisposition"] = f'attachment; filename="capture.{extension}"'
    return _client().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=settings.s3_presigned_url_ttl_seconds,
    )
