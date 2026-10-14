"""周报：趋势统计（SQL 算好）→ 组稿 → 落库。

设计要点：数字一律由数据库算好再交给模型，模型只负责叙述与分组，
避免"让模型自己数"这种必然会漂移的做法。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.daily import existing_brief_id, format_items, record_usage
from app.briefs.render import render_markdown
from app.briefs.schema import PROMPT_VERSION, BriefContent
from app.briefs.select import select_items
from app.config import get_settings
from app.llm import get_llm_client
from app.llm.base import LlmError
from app.llm.prompts import load_template
from app.models.analysis import Analysis, Cluster
from app.models.document import Document
from app.models.summary import Brief, BriefItem

log = structlog.get_logger("briefs.weekly")


@dataclass(slots=True)
class WeeklyTrends:
    period_start: datetime
    period_end: datetime
    documents: int = 0
    sources: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    rising_tags: list[tuple[str, int, int]] = field(default_factory=list)
    top_tags: list[tuple[str, int]] = field(default_factory=list)
    top_regions: list[tuple[str, int]] = field(default_factory=list)
    new_clusters: int = 0
    multi_source_clusters: int = 0
    biggest_clusters: list[tuple[int, int, list[str]]] = field(default_factory=list)
    headline_only_ratio: float = 0.0


@dataclass(slots=True)
class WeeklyBriefResult:
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


def rank_tag_deltas(
    current: dict[str, int],
    previous: dict[str, int],
    limit: int = 6,
) -> list[tuple[str, int, int]]:
    """按增量排序的话题（新出现的与增长最快的排前面）；纯函数，便于单测。"""
    deltas = [(tag, count, previous.get(tag, 0)) for tag, count in current.items()]
    deltas.sort(key=lambda item: (item[1] - item[2], item[1]), reverse=True)
    return deltas[:limit]


def format_top(items: list[tuple[str, int]]) -> str:
    return ", ".join(f"{name}({count})" for name, count in items)


def format_deltas(items: list[tuple[str, int, int]]) -> str:
    return ", ".join(f"{tag}(本周{cur}/上周{prev})" for tag, cur, prev in items)


def format_trends(trends: WeeklyTrends) -> str:
    """把统计摊平成提示词可读的文本（纯函数，便于单测）。"""
    lines: list[str] = []
    lines.append(f"- 本周入库并富化的记录：{trends.documents} 条，覆盖 {trends.sources} 个来源")
    if trends.languages:
        pairs = sorted(trends.languages.items())
        lines.append("- 语言分布：" + format_top(pairs))
    if trends.top_tags:
        lines.append("- 本周高频话题：" + format_top(trends.top_tags))
    if trends.rising_tags:
        lines.append("- 相比上周增长的话题：" + format_deltas(trends.rising_tags))
    if trends.top_regions:
        lines.append("- 地区分布：" + format_top(trends.top_regions))
    lines.append(
        f"- 事件聚类：本周新增 {trends.new_clusters} 个，其中"
        f" {trends.multi_source_clusters} 个由多个来源共同报道"
    )
    for cluster_id, count, terms in trends.biggest_clusters:
        keywords = ", ".join(terms[:4]) or "（无）"
        lines.append(f"  · cluster#{cluster_id}：{count} 条报道，关键词 {keywords}")
    if trends.headline_only_ratio > 0:
        percent = round(trends.headline_only_ratio * 100)
        lines.append(f"- 仅标题素材占比：{percent}%（这些内容只能按标题陈述）")
    return "\n".join(lines)


def latest_analysis_ids() -> Any:
    return (
        select(func.max(Analysis.id))
        .where(Analysis.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )


async def tag_counts(session: AsyncSession, since: datetime, until: datetime) -> dict[str, int]:
    latest = latest_analysis_ids()
    tag = func.unnest(Analysis.tags).label("tag")
    moment = func.coalesce(Document.published_at, Document.fetched_at)
    stmt = (
        select(tag, func.count().label("n"))
        .join(Document, Document.id == Analysis.document_id)
        .where(Analysis.id == latest)
        .where(Document.status == "enriched")
        .where(moment >= since)
        .where(moment <= until)
        .group_by(tag)
        .order_by(func.count().desc())
        .limit(40)
    )
    rows = (await session.execute(stmt)).all()
    return {str(name): int(count) for name, count in rows if name}


async def region_counts(
    session: AsyncSession, since: datetime, until: datetime
) -> list[tuple[str, int]]:
    latest = latest_analysis_ids()
    region = func.unnest(Analysis.regions).label("region")
    moment = func.coalesce(Document.published_at, Document.fetched_at)
    stmt = (
        select(region, func.count().label("n"))
        .join(Document, Document.id == Analysis.document_id)
        .where(Analysis.id == latest)
        .where(Document.status == "enriched")
        .where(moment >= since)
        .where(moment <= until)
        .group_by(region)
        .order_by(func.count().desc())
        .limit(8)
    )
    rows = (await session.execute(stmt)).all()
    return [(str(name), int(count)) for name, count in rows if name]


async def volume_stats(
    session: AsyncSession, since: datetime, until: datetime
) -> tuple[int, int, dict[str, int], float]:
    """返回 (文档数, 来源数, 语言分布, 仅标题占比)。"""
    latest = latest_analysis_ids()
    moment = func.coalesce(Document.published_at, Document.fetched_at)
    stmt = (
        select(Document, Analysis)
        .join(Analysis, Analysis.id == latest)
        .where(Document.status == "enriched")
        .where(moment >= since)
        .where(moment <= until)
    )
    rows = (await session.execute(stmt)).all()
    documents = len(rows)
    sources = len({doc.source_id for doc, _analysis in rows if doc.source_id is not None})
    languages: dict[str, int] = {}
    headline_only = 0
    for doc, analysis in rows:
        lang = doc.language or "und"
        languages[lang] = languages.get(lang, 0) + 1
        if "headline-only" in list(analysis.tags or []):
            headline_only += 1
    ratio = (headline_only / documents) if documents else 0.0
    return documents, sources, languages, ratio


async def compute_trends(session: AsyncSession, *, now: datetime | None = None) -> WeeklyTrends:
    """算好本周统计（含与上周的对比）。"""
    settings = get_settings()
    moment = now or datetime.now(UTC)
    period_end = moment
    period_start = moment - timedelta(days=settings.weekly_lookback_days)
    prev_start = period_start - timedelta(days=settings.weekly_lookback_days)

    trends = WeeklyTrends(period_start=period_start, period_end=period_end)
    current_tags = await tag_counts(session, period_start, period_end)
    previous_tags = await tag_counts(session, prev_start, period_start)
    trends.top_tags = sorted(current_tags.items(), key=lambda item: item[1], reverse=True)[:8]
    trends.rising_tags = rank_tag_deltas(current_tags, previous_tags)
    trends.top_regions = await region_counts(session, period_start, period_end)
    (
        trends.documents,
        trends.sources,
        trends.languages,
        trends.headline_only_ratio,
    ) = await volume_stats(session, period_start, period_end)

    new_clusters = (
        await session.execute(
            select(func.count())
            .select_from(Cluster)
            .where(Cluster.first_seen_at >= period_start)
            .where(Cluster.first_seen_at <= period_end)
        )
    ).scalar_one()
    trends.new_clusters = int(new_clusters or 0)

    big_rows = (
        await session.execute(
            select(Cluster.id, Cluster.doc_count, Cluster.key_terms)
            .where(Cluster.first_seen_at >= period_start)
            .where(Cluster.doc_count > 1)
            .order_by(Cluster.doc_count.desc())
            .limit(5)
        )
    ).all()
    trends.biggest_clusters = [
        (int(cid), int(count), list(terms or [])) for cid, count, terms in big_rows
    ]
    trends.multi_source_clusters = len(trends.biggest_clusters)
    return trends


async def generate_weekly_brief(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> WeeklyBriefResult:
    """生成周报；默认幂等（同一自然周已有就跳过）。"""
    settings = get_settings()
    moment = now or datetime.now(UTC)
    if not force:
        week_start = moment.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=moment.weekday()
        )
        existing = await existing_brief_id(session, week_start, kind="weekly")
        if existing is not None:
            return WeeklyBriefResult(brief_id=existing, created=False, reason="already_exists")

    trends = await compute_trends(session, now=moment)
    items = await select_items(
        session,
        since=trends.period_start,
        until=trends.period_end,
        limit=settings.weekly_top_items,
    )
    if not items:
        brief = Brief(
            kind="weekly",
            period_start=trends.period_start,
            period_end=trends.period_end,
            language="bilingual",
            title="本周没有可用的新内容",
            markdown="# 本周没有可用的新内容\n\n时间窗内没有通过筛选的记录。\n",
            structured={"reason": "no_items"},
            model="none",
            prompt_version=PROMPT_VERSION,
        )
        session.add(brief)
        await session.flush()
        return WeeklyBriefResult(brief_id=brief.id, created=True, reason="no_items")

    template = load_template("brief_weekly")
    period_text = (
        trends.period_start.strftime("%Y-%m-%d") + " ~ " + trends.period_end.strftime("%Y-%m-%d")
    )
    system = template.format(
        period=period_text + " UTC",
        stats=format_trends(trends),
        items=format_items(items),
    )
    llm = get_llm_client()
    try:
        payload, usage, repaired = await llm.complete_json(
            kind="brief",
            system=system,
            user="请按上面的要求输出本周周报 JSON。",
            model=settings.llm_model_brief,
        )
    except LlmError as exc:
        log.warning("weekly_brief.llm_failed", error=str(exc)[:200])
        raise

    try:
        content = BriefContent.model_validate(payload)
    except ValidationError as exc:
        detail = str(exc.errors()[:2])[:300]
        raise LlmError("周报输出校验失败：" + detail) from exc

    markdown = render_markdown(
        content, language="zh", items=items, period=(trends.period_start, trends.period_end)
    )
    brief = Brief(
        kind="weekly",
        period_start=trends.period_start,
        period_end=trends.period_end,
        language="bilingual",
        title=content.title_zh or "humanpulse 周报",
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
        "weekly_brief.created",
        brief_id=brief.id,
        items=len(items),
        repaired=repaired,
        model=usage.model,
    )
    return WeeklyBriefResult(
        brief_id=brief.id,
        created=True,
        item_count=len(items),
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
    )
