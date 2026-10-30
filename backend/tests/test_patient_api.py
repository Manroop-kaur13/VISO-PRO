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


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/register", json={"email": email, "password": "CorrectHorseBatteryStaple!"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_patient_and_profile_are_saved_and_private(client: TestClient) -> None:
    clinician_headers = _register(client, "clinician@example.com")
    created = client.post(
        "/api/patients",
        headers=clinician_headers,
        json={
            "patient_id": "VISO-001",
            "patient_name": "Test Patient",
            "age": 42,
            "examination": "Ophthalmic Examination",
        },
    )
    assert created.status_code == 201
    assert created.json()["patient_id"] == "VISO-001"

    notes = client.put(
        "/api/patients/VISO-001/profile",
        headers=clinician_headers,
        json={
            "comments": "Synthetic test note",
            "annotations": [
                {"kind": "marker", "x": 250, "y": 300},
                {"kind": "text", "x": 410, "y": 220, "note": "synthetic annotation"},
            ],
        },
    )
    assert notes.status_code == 200
    session_id = notes.json()["session_id"]
    assert notes.json()["comments"] == "Synthetic test note"
    assert notes.json()["captures"] == []

    profile = client.get("/api/patients/VISO-001/profile", headers=clinician_headers)
    assert profile.status_code == 200
    assert profile.json()["session_id"] == session_id
    assert len(profile.json()["annotations"]) == 2

    other_headers = _register(client, "other-clinician@example.com")
    assert client.get("/api/patients", headers=other_headers).json() == []
    assert client.get("/api/patients/VISO-001/profile", headers=other_headers).status_code == 404


def test_patient_endpoints_require_authentication_and_validate_fields(client: TestClient) -> None:
    assert client.get("/api/patients").status_code == 401
    headers = _register(client, "clinician@example.com")
    invalid = client.post(
        "/api/patients",
        headers=headers,
        json={"patient_id": "VISO-BAD", "patient_name": "Bad Age", "age": 200},
    )
    assert invalid.status_code == 422
    blank_name = client.post(
        "/api/patients",
        headers=headers,
        json={"patient_id": "VISO-BLANK", "patient_name": "   "},
    )
    assert blank_name.status_code == 422
    unsafe_id = client.post(
        "/api/patients",
        headers=headers,
        json={"patient_id": "VISO/unsafe", "patient_name": "Synthetic Patient"},
    )
    assert unsafe_id.status_code == 422


def test_upload_rejects_unapproved_file_types(client: TestClient) -> None:
    headers = _register(client, "clinician@example.com")
    patient = client.post(
        "/api/patients",
        headers=headers,
        json={"patient_id": "VISO-002", "patient_name": "Synthetic Patient"},
    )
    assert patient.status_code == 201
    response = client.post(
        "/api/patients/VISO-002/captures",
        headers=headers,
        data={"client_capture_id": "capture-1"},
        files={"file": ("capture.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_download_and_delete_use_private_storage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.storage import s3

    monkeypatch.setenv("VISO_S3_BUCKET", "synthetic-test-bucket")
    get_settings.cache_clear()
    uploaded: dict[str, bytes] = {}
    monkeypatch.setattr(s3, "put_object", lambda key, data, content_type: uploaded.update({key: data}))
    monkeypatch.setattr(
        s3,
        "signed_download_url",
        lambda key, as_attachment=False: f"https://storage.invalid/{key}",
    )
    monkeypatch.setattr(s3, "delete_object", lambda key: uploaded.pop(key, None))

    headers = _register(client, "capture@example.com")
    created = client.post(
        "/api/patients",
        headers=headers,
        json={"patient_id": "SYN-IMG", "patient_name": "Synthetic Test"},
    )
    assert created.status_code == 201
    response = client.post(
        "/api/patients/SYN-IMG/captures",
        headers=headers,
        data={"client_capture_id": "camera-capture-1"},
        files={
            "file": (
                "capture.png",
                bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"synthetic",
                "image/png",
            )
        },
    )
    assert response.status_code == 201
    image_id = response.json()["image_id"]
    assert response.json()["image_url"].startswith("https://storage.invalid/")
    assert len(uploaded) == 1

    listed = client.get("/api/patients/SYN-IMG/captures", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    download = client.get(
        f"/api/patients/SYN-IMG/captures/{image_id}/download",
        headers=headers,
        follow_redirects=False,
    )
    assert download.status_code == 200
    assert download.json()["url"].startswith("https://storage.invalid/")

    deleted = client.delete(
        f"/api/patients/SYN-IMG/captures/{image_id}", headers=headers
    )
    assert deleted.status_code == 204
    assert uploaded == {}
    assert client.get("/api/patients/SYN-IMG/captures", headers=headers).json() == []
    get_settings.cache_clear()