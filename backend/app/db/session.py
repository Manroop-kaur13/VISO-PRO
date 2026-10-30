"""Database engine and FastAPI session dependency."""

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=4)
def create_database_engine(database_url: str) -> Engine:
    """Build an engine; PostgreSQL connections verify TLS through the URL options."""
    # Providers commonly supply postgresql:// URLs. This project installs
    # psycopg 3, so select that driver explicitly when none is named.
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return create_engine(database_url, pool_pre_ping=True)


def database_is_reachable() -> bool:
    """Return whether a configured database accepts a trivial connection."""

    database_url = get_settings().database_url
    if not database_url:
        return False
    try:
        with create_database_engine(database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def get_db() -> Generator[Session, None, None]:
    """Yield a short-lived session or report an unavailable database clearly."""

    database_url = get_settings().database_url
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
    engine = create_database_engine(database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
