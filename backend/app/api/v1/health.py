from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app import __version__
from app.config import get_settings
from app.db import ping
from app.schemas.health import ComponentStatus, HealthResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="存活探针")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        version=__version__,
        env=settings.env,
        time=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="就绪探针（含数据库连通性）",
    responses={503: {"description": "依赖不可用"}},
)
async def ready(response: Response) -> ReadyResponse:
    db_ok = await ping()
    components = [ComponentStatus(name="database", ok=db_ok)]
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ready" if db_ok else "degraded", components=components)
