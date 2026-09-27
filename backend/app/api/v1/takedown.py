"""合规入口：删除/屏蔽申请（公开提交，人工处理）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.ops import TakedownRequest
from app.schemas.content import TakedownIn, TakedownOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/takedown", response_model=TakedownOut, summary="提交内容删除/屏蔽申请")
async def create_takedown(payload: TakedownIn, session: SessionDep) -> TakedownOut:
    row = TakedownRequest(
        target_url=payload.target_url,
        reason=payload.reason,
        requester=payload.requester,
        status="open",
    )
    session.add(row)
    await session.flush()
    return TakedownOut(id=row.id, status=row.status)
