"""脉搏监控：实时检测实体提及频率异常，触发自动推演。"""

from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.projection import generate_projection
from app.briefs.select import SelectedItem
from app.models.document import Document
from app.models.entity import EntityMention

log = structlog.get_logger("pipeline.pulse")


async def calculate_z_score(session: AsyncSession, entity_id: int) -> float:
    """计算实体的 Z-Score (当前频率 vs 历史平均)。"""
    # 1. 计算过去 7 天的日均提及数
    from datetime import timedelta

    stmt = (
        select(func.count(EntityMention.id))
        .where(EntityMention.entity_id == entity_id)
        .where(EntityMention.created_at >= func.now() - timedelta(days=7))
    )
    total = (await session.execute(stmt)).scalar() or 0
    mean = total / 7.0

    # 2. 计算今日提及数
    stmt_today = (
        select(func.count(EntityMention.id))
        .where(EntityMention.entity_id == entity_id)
        .where(EntityMention.created_at >= func.date_trunc("day", func.now()))
    )
    today = (await session.execute(stmt_today)).scalar() or 0

    if mean <= 0:
        return 0.0 if today <= 0 else 10.0

    import math

    return (today - mean) / math.sqrt(mean)


async def monitor_pulse(session: AsyncSession) -> None:
    """扫描高频实体，触发异常推演。"""
    stmt = (
        select(EntityMention.entity_id, func.count(EntityMention.id).label("count"))
        .where(EntityMention.created_at >= func.date_trunc("day", func.now()))
        .group_by(EntityMention.entity_id)
        .having(func.count(EntityMention.id) > 5)
        .order_by(func.count(EntityMention.id).desc())
    )
    entities = (await session.execute(stmt)).all()

    for entity_id, _count in entities:
        z = await calculate_z_score(session, entity_id)
        if z > 3.0:
            log.info("pulse.anomaly_detected", entity_id=entity_id, z_score=z)
            # 触发推演：选取该实体最相关的文档
            stmt_doc = (
                select(Document)
                .join(EntityMention)
                .where(EntityMention.entity_id == entity_id)
                .order_by(Document.published_at.desc())
                .limit(1)
            )
            doc = (await session.execute(stmt_doc)).scalar()
            if doc:
                item = SelectedItem(
                    document_id=doc.id,
                    cluster_id=None,
                    title=doc.title,
                    summary_zh="",
                    summary_en="",
                    score=0,
                    source_name=None,
                    url=doc.url,
                    published_at=doc.published_at,
                    headline_only=True,
                )
                await generate_projection(
                    [item],
                    horizon_days=14,
                    max_events=3,
                    hops=3,
                    min_confidence=0.6,
                )
