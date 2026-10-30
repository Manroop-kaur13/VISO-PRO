"""Registration, login, logout, and current-user endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    token_expiry,
    verify_password,
)
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.schemas.auth import Credentials, CurrentUser, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


def _issue_session(user: User, db: Session) -> TokenResponse:
    expires_at = token_expiry()
    session_id = uuid4()
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires_at))
    token = create_access_token(user.id, session_id, expires_at)
    db.commit()
    ttl = get_settings().auth_token_ttl_minutes * 60
    return TokenResponse(access_token=token, expires_in=ttl)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id, session_id, token_expires_at = decode_access_token(credentials.credentials)
    auth_session = db.get(AuthSession, session_id)
    now = datetime.now(timezone.utc)
    session_expires_at = auth_session.expires_at if auth_session is not None else now
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=timezone.utc)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or session_expires_at <= now
        or token_expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable.")
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(credentials: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(credentials.email).strip().lower()
    user = User(email=email, hashed_password=hash_password(credentials.password))
    db.add(user)
    try:
        db.flush()
        return _issue_session(user, db)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc


@router.post("/login", response_model=TokenResponse)
def login(credentials: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = str(credentials.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is unavailable.")
    return _issue_session(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Response:
    # get_current_user already validated the token; decode again to identify its session.
    assert credentials is not None
    _, session_id, _ = decode_access_token(credentials.credentials)
    auth_session = db.get(AuthSession, session_id)
    if auth_session is not None:
        auth_session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=CurrentUser)
def current_user(user: User = Depends(get_current_user)) -> User:
    return user
