"""日报生成：选材 → 组稿 → 落库。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.render import render_markdown
from app.briefs.schema import PROMPT_VERSION, BriefContent
from app.briefs.select import SelectedItem, select_items
from app.config import get_settings
from app.llm import get_llm_client
from app.llm.base import LlmError, LlmUsage
from app.llm.prompts import load_template
from app.models.ops import LlmUsageDay
from app.models.summary import Brief, BriefItem

log = structlog.get_logger("briefs.daily")


@dataclass(slots=True)
class DailyBriefResult:
    brief_id: int | None = None
    created: bool = False
    item_count: int = 0
    reason: str = ""
    tokens_in: int = 0
    tokens_out: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "created": self.created,
            "item_count": self.item_count,
            "reason": self.reason,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


def format_items(items: list[SelectedItem]) -> str:
    """把素材摊平成提示词可读的清单（纯函数，便于单测）。"""
    blocks: list[str] = []
    for index, item in enumerate(items, start=1):
        flag = "（仅据标题）" if item.headline_only else ""
        source = item.source_name or "unknown"
        blocks.append(
            "\n".join(
                [
                    f"{index}. 标题：{item.title}{flag}",
                    f"   来源：{source}｜评分：{item.score}｜链接：{item.url}",
                    f"   中文摘要：{item.summary_zh or ('（无）')}",
                    f"   English summary: {item.summary_en or '(none)'}",
                ]
            )
        )
    return "\n\n".join(blocks)


async def record_usage(session: AsyncSession, usage: LlmUsage) -> None:
    stmt = pg_insert(LlmUsageDay).values(
        day=datetime.now(UTC).date(),
        provider=usage.provider,
        model=usage.model,
        calls=1,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        cost_usd=usage.cost_usd,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_llm_usage_day_model",
        set_={
            "calls": LlmUsageDay.calls + stmt.excluded.calls,
            "tokens_in": LlmUsageDay.tokens_in + stmt.excluded.tokens_in,
            "tokens_out": LlmUsageDay.tokens_out + stmt.excluded.tokens_out,
            "cost_usd": LlmUsageDay.cost_usd + stmt.excluded.cost_usd,
        },
    )
    await session.execute(stmt)


async def existing_brief_id(
    session: AsyncSession, start: datetime, *, kind: str = "daily"
) -> int | None:
    """同一周期内是否已有简报（日报看当天、周报看本周），用于幂等。"""
    stmt = select(Brief.id).where(Brief.kind == kind).where(Brief.period_start >= start)
    return (await session.execute(stmt)).scalars().first()


async def generate_daily_brief(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> DailyBriefResult:
    """生成当日日报；默认幂等（同一天已有就跳过）。"""
    settings = get_settings()
    moment = now or datetime.now(UTC)
    period_end = moment
    period_start = moment - timedelta(hours=settings.brief_lookback_hours)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)

    if not force:
        existing = await existing_brief_id(session, day_start)
        if existing is not None:
            return DailyBriefResult(brief_id=existing, created=False, reason="already_exists")

    items = await select_items(
        session, since=period_start, until=period_end, limit=settings.brief_top_items
    )
    if not items:
        # 没有素材也留痕，避免"静默什么都没发生"。
        brief = Brief(
            kind="daily",
            period_start=period_start,
            period_end=period_end,
            language="bilingual",
            title="本期没有可用的新内容",
            markdown="# 本期没有可用的新内容\n\n时间窗内没有通过筛选的记录。\n",
            structured={"reason": "no_items"},
            model="none",
            prompt_version=PROMPT_VERSION,
        )
        session.add(brief)
        await session.flush()
        return DailyBriefResult(brief_id=brief.id, created=True, reason="no_items")

    template = load_template("brief_daily")
    system = template.format(
        period=f"{period_start:%Y-%m-%d %H:%M} ~ {period_end:%Y-%m-%d %H:%M} UTC",
        items=format_items(items),
    )
    llm = get_llm_client()
    try:
        payload, usage, repaired = await llm.complete_json(
            kind="brief",
            system=system,
            user="请按上面的要求输出当期日报 JSON。",
            model=settings.llm_model_brief,
        )
    except LlmError as exc:
        log.warning("brief.llm_failed", error=str(exc)[:200])
        raise

    try:
        content = BriefContent.model_validate(payload)
    except ValidationError as exc:
        detail = str(exc.errors()[:2])[:300]
        raise LlmError("简报输出校验失败：" + detail) from exc

    markdown = render_markdown(
        content, language="zh", items=items, period=(period_start, period_end)
    )
    brief = Brief(
        kind="daily",
        period_start=period_start,
        period_end=period_end,
        language="bilingual",
        title=content.title_zh or "humanpulse 日报",
        markdown=markdown,
        structured=json.loads(content.model_dump_json()),
        model=usage.model,
        prompt_version=PROMPT_VERSION,
        cost_usd=usage.cost_usd,
    )
    session.add(brief)
    await session.flush()
    for rank, item in enumerate(items, start=1):
        session.add(
            BriefItem(
                brief_id=brief.id,
                document_id=item.document_id,
                cluster_id=item.cluster_id,
                rank=rank,
                rationale=f"score={item.score}",
            )
        )
    await record_usage(session, usage)
    await session.flush()

    # 预测登记（P3 校准样本积累）：判官未配置时静默跳过；不发布推演（projection_enabled=false）
    # 局部导入避免 app.briefs ↔ app.predictions 的循环依赖
    from app.predictions import register_brief_projection

    await register_brief_projection(session, items, brief_id=brief.id)

    log.info(
        "brief.created",
        brief_id=brief.id,
        items=len(items),
        repaired=repaired,
        model=usage.model,
    )
    return DailyBriefResult(
        brief_id=brief.id,
        created=True,
        item_count=len(items),
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
    )
