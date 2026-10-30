from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("VISO_AUTH_TOKEN_SECRET", "test-secret-with-enough-entropy-1234567890")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def test_register_login_current_user_and_revocable_logout(client: TestClient) -> None:
    registration = client.post(
        "/auth/register",
            json={"email": "Clinician@example.com", "password": "CorrectHorseBatteryStaple!"},
    )
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    assert registration.json()["token_type"] == "bearer"
    assert registration.json()["expires_in"] == 1800

    headers = {"Authorization": f"Bearer {token}"}
    profile = client.get("/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["email"] == "clinician@example.com"
    assert profile.json()["role"] == "clinician"
    assert "hashed_password" not in profile.json()

    login = client.post(
        "/auth/login",
        json={"email": "clinician@example.com", "password": "CorrectHorseBatteryStaple!"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"] != token

    logout = client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_duplicate_registration_and_invalid_login_are_rejected(client: TestClient) -> None:
    payload = {"email": "clinician@example.com", "password": "CorrectHorseBatteryStaple!"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409
    bad_login = client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "WrongPasswordString!"},
    )
    assert bad_login.status_code == 401


def test_registration_requires_a_long_valid_password(client: TestClient) -> None:
    short_password = client.post(
        "/auth/register", json={"email": "short@example.com", "password": "short"}
    )
    assert short_password.status_code == 422


def test_protected_profile_requires_a_valid_bearer_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_registration_rejects_client_selected_roles(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "role@example.com",
            "password": "CorrectHorseBatteryStaple!",
            "role": "admin",
        },
    )
    assert response.status_code == 422
