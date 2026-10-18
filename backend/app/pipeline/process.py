"""LLM 富化 + 向量化 + 聚类：把 pending 文档变成可读条目。

单批并发策略：LLM 调用是主要耗时（实测串行约 5.4s/条），因此先用信号量并发取回结果，
再顺序落库——数据库写入保持在单会话里顺序执行，避免竞态。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embedding import get_embedder
from app.llm import get_llm_client
from app.llm.base import AnalyzeResult, LlmClient, LlmError, LlmUsage
from app.llm.schema import PROMPT_VERSION
from app.models.analysis import Analysis, Embedding
from app.models.document import Document
from app.models.ops import LlmUsageDay
from app.pipeline.dedup import attach_cluster, embedding_text
from app.pipeline.entities import upsert_entities

log = structlog.get_logger("pipeline.process")

MIN_TEXT_CHARS = 40
# 只有标题可用的条目（例如 GDELT 只给域名）走 headline 提示词，并打上标记标签：
# 宁可让摘要明确“仅据标题”，也不要让模型在缺少正文时编造细节。
MIN_TITLE_CHARS = 15
HEADLINE_TAG = "headline-only"


@dataclass(slots=True)
class ProcessStats:
    picked: int = 0
    enriched: int = 0
    rejected: int = 0
    failed: int = 0
    skipped_budget: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "picked": self.picked,
            "enriched": self.enriched,
            "rejected": self.rejected,
            "failed": self.failed,
            "skipped_budget": self.skipped_budget,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


@dataclass(slots=True)
class WorkItem:
    """一次 LLM 调用的输入。"""

    document: Document
    text: str
    prompt_kind: str
    headline_only: bool


def plan_document(document: Document) -> WorkItem | None:
    """决定这条文档要不要调 LLM、用哪个提示词；返回 None 表示内容太短、直接拒绝。"""
    body = (document.excerpt or "").strip()
    title = document.title.strip()
    headline_only = len(body) < MIN_TEXT_CHARS
    if headline_only and len(title) < MIN_TITLE_CHARS:
        return None
    if headline_only:
        # 只有标题时把来源域名一并交给模型，并要求它在摘要里标明"仅据标题"
        text = f"{title}\n\n[仅标题可用] 来源域名：{body or 'unknown'}"
        return WorkItem(document=document, text=text, prompt_kind="headline", headline_only=True)
    return WorkItem(
        document=document,
        text=f"{title}\n\n{body}",
        prompt_kind=document.kind,
        headline_only=False,
    )


async def _analyze_one(
    semaphore: asyncio.Semaphore, llm: LlmClient, item: WorkItem
) -> tuple[WorkItem, AnalyzeResult | None, str | None]:
    """在信号量保护下调用 LLM；错误不抛出，转成字符串交给落库阶段标记状态。"""
    async with semaphore:
        try:
            result = await llm.analyze(
                kind=item.prompt_kind,
                title=item.document.title,
                text=item.text,
                url=item.document.url,
            )
        except LlmError as exc:
            return item, None, f"llm_error: {str(exc)[:200]}"
        except Exception as exc:
            return item, None, f"provider_error: {str(exc)[:200]}"
    return item, result, None


async def _record_usage(session: AsyncSession, usage: LlmUsage) -> None:
    """累加当日用量。

    用 INSERT ... ON CONFLICT 而不是 SELECT+INSERT：worker 与管理接口可能同时处理，
    先查后写会撞 uq_llm_usage_day_model（实测发生过，整批结果因此丢失）。
    """
    stmt = pg_insert(LlmUsageDay).values(
        day=date.today(),
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


async def _tokens_used_today(session: AsyncSession) -> int:
    stmt = select(func.coalesce(func.sum(LlmUsageDay.tokens_in + LlmUsageDay.tokens_out), 0)).where(
        LlmUsageDay.day == date.today()
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def process_pending(session: AsyncSession, *, limit: int = 20) -> ProcessStats:
    """处理一批 pending 文档：并发调 LLM，顺序落库；单条失败不影响整批。"""
    settings = get_settings()
    stats = ProcessStats()

    docs = (
        (
            await session.execute(
                select(Document)
                .where(Document.status == "pending")
                .order_by(
                    # 混合策略：优先处理最老的 30%（清积压），其余取最新的（保新鲜度）
                    case(
                        (Document.created_at < (func.now() - timedelta(days=3)), 0),
                        else_=1,
                    ).asc(),
                    Document.created_at.asc(),
                    Document.id.asc(),
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    stats.picked = len(docs)
    if not docs:
        return stats

    used_today = await _tokens_used_today(session)
    if used_today >= settings.llm_daily_token_budget:
        stats.skipped_budget = len(docs)
        log.warning(
            "llm.budget_exceeded",
            used_today=used_today,
            budget=settings.llm_daily_token_budget,
        )
        return stats

    llm = get_llm_client()
    embedder = get_embedder()

    items: list[WorkItem] = []
    for document in docs:
        planned = plan_document(document)
        if planned is None:
            document.status = "rejected"
            document.rejection_reason = "too_short"
            stats.rejected += 1
            continue
        items.append(planned)

    if items:
        semaphore = asyncio.Semaphore(settings.llm_concurrency)
        outcomes = await asyncio.gather(*(_analyze_one(semaphore, llm, item) for item in items))
    else:
        outcomes = []

    for item, result, error in outcomes:
        document = item.document
        if result is None:
            document.status = "failed"
            document.rejection_reason = (
                "llm_error" if (error or "").startswith("llm_error") else "provider_error"
            )
            stats.failed += 1
            log.warning("llm.failed", document_id=document.id, error=(error or "")[:200])
            continue

        data = result.data
        tags = list(data.tags)
        if item.headline_only and HEADLINE_TAG not in tags:
            tags.append(HEADLINE_TAG)
        stats.tokens_in += result.usage.tokens_in
        stats.tokens_out += result.usage.tokens_out
        await _record_usage(session, result.usage)

        analysis = Analysis(
            document_id=document.id,
            prompt_version=PROMPT_VERSION,
            provider=result.usage.provider,
            model=result.usage.model,
            relevant=data.relevant,
            score=data.score,
            summary_zh=data.summary_zh,
            summary_en=data.summary_en,
            tags=tags,
            regions=data.regions,
            rationale=data.rationale,
            entities=[entity.model_dump() for entity in data.entities],
            tokens_in=result.usage.tokens_in,
            tokens_out=result.usage.tokens_out,
            cost_usd=result.usage.cost_usd,
        )
        session.add(analysis)
        await session.flush()

        if not data.relevant or data.score <= 0:
            document.status = "rejected"
            document.rejection_reason = "low_relevance"
            stats.rejected += 1
            continue

        # 只有通过相关性筛选的文档才写入实体时间线，避免噪音实体污染
        await upsert_entities(
            session,
            document=document,
            analysis_id=analysis.id,
            entities=[entity.model_dump() for entity in data.entities],
        )

        vector = embedder.embed(
            embedding_text(data.summary_zh, data.summary_en, tags, document.title)
        )
        session.add(
            Embedding(
                analysis_id=analysis.id,
                document_id=document.id,
                model=embedder.name,
                dim=len(vector),
                vec=vector,
            )
        )
        await session.flush()
        await attach_cluster(session, document=document, vec=vector, key_terms=data.tags[:3])
        document.status = "enriched"
        stats.enriched += 1

    await session.flush()
    log.info("pipeline.process.done", **stats.as_dict())
    return stats


def now_utc() -> datetime:
    return datetime.now(UTC)
