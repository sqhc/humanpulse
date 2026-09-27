"""接口依赖：管理员鉴权。"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings


async def require_admin(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """写操作统一走这里；用 compare_digest 避免时序侧信道。"""
    settings = get_settings()
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key（写操作需要 X-API-Key）",
        )


AdminDep = Annotated[None, Depends(require_admin)]
