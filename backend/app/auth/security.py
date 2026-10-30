"""Password hashing and short-lived, revocable access tokens."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.config import get_settings

password_hash = PasswordHash.recommended()
TOKEN_ISSUER = "viso-pro-api"
TOKEN_AUDIENCE = "viso-pro"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def _secret() -> str:
    configured = get_settings().auth_token_secret
    secret = configured.get_secret_value() if configured else ""
    insecure_placeholders = {
        "generate_a_random_secret_for_local_development",
        "replace_with_at_least_32_random_characters",
    }
    if len(secret) < 32 or secret in insecure_placeholders:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )
    return secret


def create_access_token(user_id: UUID, session_id: UUID, expires_at: datetime) -> str:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued_at,
            "exp": expires_at,
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
        },
        _secret(),
        algorithm="HS256",
    )


def decode_access_token(token: str) -> tuple[UUID, UUID, datetime]:
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
        )
        user_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        return user_id, session_id, expires_at
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        minutes=get_settings().auth_token_ttl_minutes
    )
