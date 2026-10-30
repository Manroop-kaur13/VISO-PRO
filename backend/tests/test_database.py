from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import User
from app.db.session import create_database_engine


def test_user_table_creates_and_stores_a_clinician() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="clinician@example.test", hashed_password="test-hash")
        session.add(user)
        session.commit()
        saved = session.get(User, user.id)
        assert saved is not None
        assert saved.email == "clinician@example.test"
        assert saved.role == "clinician"
        assert saved.is_active is True

    engine.dispose()


def test_user_table_rejects_roles_outside_the_supported_set() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            User(email="unknown@example.test", hashed_password="test-hash", role="patient")
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Unsupported roles must be rejected by the database.")

    engine.dispose()


def test_provider_postgresql_urls_use_installed_psycopg_driver() -> None:
    for scheme in ("postgres://", "postgresql://"):
        engine = create_database_engine(f"{scheme}viso_app:example@db.invalid/viso_db")
        try:
            assert engine.dialect.name == "postgresql"
            assert engine.dialect.driver == "psycopg"
        finally:
            engine.dispose()
