from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app

client = TestClient(app)


def test_health_check_confirms_process_is_alive() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_does_not_claim_unconfigured_services_are_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.health.get_settings",
        lambda: Settings(database_url=None),
    )
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "api": "ready",
            "database": "not_configured",
            "object_storage_configuration": "not_configured",
            "object_storage": "not_configured",
        },
    }


def test_readiness_distinguishes_cloudinary_configuration_from_connectivity(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.health.get_settings",
        lambda: Settings(database_url=None, cloudinary_cloud_name="cloud", cloudinary_api_key="key"),
    )
    monkeypatch.setattr("app.api.routes.health.storage.storage_is_configured", lambda: True)
    monkeypatch.setattr("app.api.routes.health.storage.storage_is_ready", lambda: False)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["object_storage_configuration"] == "configured"
    assert response.json()["checks"]["object_storage"] == "unavailable"


def test_cors_allows_the_deployed_frontend_origin() -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "https://viso-pro.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://viso-pro.vercel.app"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_reflect_an_unconfigured_origin() -> None:
    response = client.get("/health", headers={"Origin": "https://untrusted.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_openapi_documents_health_routes() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
    assert "/ready" in response.json()["paths"]
