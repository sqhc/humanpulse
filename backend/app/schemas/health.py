from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "humanpulse-api"
    version: str
    env: str
    time: datetime = Field(description="服务端 UTC 时间")


class ComponentStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded"]
    components: list[ComponentStatus]
