"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.config import get_settings
from app.db.session import database_is_reachable
from app import storage

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ready", "configured", "not_configured", "unavailable"]]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check whether the API process is alive",
)
def health_check() -> HealthResponse:
    """Liveness check used by the platform to confirm the process is running."""

    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Check whether required backend services are configured",
)
def readiness_check(response: Response) -> ReadinessResponse:
    """Report database and private object-storage connectivity."""

    settings = get_settings()
    if not settings.database_url:
        database_status = "not_configured"
    elif database_is_reachable():
        database_status = "ready"
    else:
        database_status = "unavailable"
    if not storage.storage_is_configured():
        storage_configuration = "not_configured"
        storage_status = "not_configured"
    else:
        storage_configuration = "configured"
        storage_status = "ready" if storage.storage_is_ready() else "unavailable"
    checks = {
        "api": "ready",
        "database": database_status,
        "object_storage_configuration": storage_configuration,
        "object_storage": storage_status,
    }
    ready = all(value == "ready" for value in checks.values())
    response.status_code = 200 if ready else 503

    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=checks,
    )
