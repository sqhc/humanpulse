"""预测登记读取接口：列表与校准汇总。

这是「推演可被证伪」对外的窗口：任何人都能看到我们登记过什么预测、
到期核对的结果如何、以及整体概率质量（Brier / 校准曲线）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.prediction import PREDICTION_STATUSES, Prediction
from app.predictions import calibration_summary

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _to_out(prediction: Prediction) -> dict[str, object]:
    return {
        "id": prediction.id,
        "brief_id": prediction.brief_id,
        "document_id": prediction.document_id,
        "cluster_id": prediction.cluster_id,
        "hop": prediction.hop,
        "question_key": prediction.question_key,
        "statement_zh": prediction.statement_zh,
        "statement_en": prediction.statement_en,
        "predicted_probability": float(prediction.predicted_probability),
        "confidence": (float(prediction.confidence) if prediction.confidence is not None else None),
        "horizon_days": prediction.horizon_days,
        "due_at": prediction.due_at.isoformat(),
        "status": prediction.status,
        "resolved_at": prediction.resolved_at.isoformat() if prediction.resolved_at else None,
        "resolved_probability": (
            float(prediction.resolved_probability)
            if prediction.resolved_probability is not None
            else None
        ),
        "brier": float(prediction.brier) if prediction.brier is not None else None,
        "provider": prediction.provider,
        "model": prediction.model,
    }


@router.get("/predictions", summary="预测登记列表")
async def list_predictions(
    session: SessionDep,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    """列出预测；status 可选，用于只看待核对/已判定。"""
    statement = select(Prediction)
    if status:
        if status not in PREDICTION_STATUSES:
            raise HTTPException(status_code=400, detail=f"未知状态：{status}")
        statement = statement.where(Prediction.status == status)
    statement = statement.order_by(Prediction.due_at.desc(), Prediction.id.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()

    total = (await session.execute(select(func.count()).select_from(Prediction))).scalar() or 0
    return {"total": int(total), "items": [_to_out(row) for row in rows]}


@router.get("/predictions/calibration", summary="预测校准汇总")
async def get_calibration(session: SessionDep) -> dict[str, object]:
    """校准汇总：Brier、基率、可靠性曲线、各状态计数。

    注意这里只统计**已判定**的预测；未判定的单独计数，不混进 Brier 里充数。
    """
    return await calibration_summary(session)
