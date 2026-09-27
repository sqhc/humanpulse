"""LLM 富化 + 向量化 + 聚类：把 pending 文档变成可读条目。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embedding import get_embedder
from app.llm import get_llm_client
from app.llm.base import LlmError, LlmUsage
from app.llm.schema import PROMPT_VERSION
from app.models.analysis import Analysis, Embedding
from app.models.document import Document
from app.models.ops import LlmUsageDay
from app.pipeline.dedup import attach_cluster, embedding_text

log = structlog.get_logger("pipeline.process")

MIN_TEXT_CHARS = 40


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


async def _record_usage(session: AsyncSession, usage: LlmUsage) -> None:
    today = date.today()
    stmt = select(LlmUsageDay).where(
        LlmUsageDay.day == today,
        LlmUsageDay.provider == usage.provider,
        LlmUsageDay.model == usage.model,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        session.add(
            LlmUsageDay(
                day=today,
                provider=usage.provider,
                model=usage.model,
                calls=1,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
                cost_usd=usage.cost_usd,
            )
        )
        return
    row.calls += 1
    row.tokens_in += usage.tokens_in
    row.tokens_out += usage.tokens_out
    row.cost_usd = Decimal(row.cost_usd or 0) + usage.cost_usd


async def _tokens_used_today(session: AsyncSession) -> int:
    stmt = select(func.coalesce(func.sum(LlmUsageDay.tokens_in + LlmUsageDay.tokens_out), 0)).where(
        LlmUsageDay.day == date.today()
    )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def process_pending(session: AsyncSession, *, limit: int = 20) -> ProcessStats:
    """按（发布时间倒序）处理 pending 文档，单条失败不影响整批。"""
    settings = get_settings()
    stats = ProcessStats()

    docs = (
        (
            await session.execute(
                select(Document)
                .where(Document.status == "pending")
                .order_by(
                    func.coalesce(Document.published_at, Document.fetched_at).desc(),
                    Document.id.asc(),
                )
                .limit(limit)
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

    for document in docs:
        body = (document.excerpt or "").strip()
        text = f"{document.title}\n\n{body}".strip()
        if len(body) < MIN_TEXT_CHARS:
            document.status = "rejected"
            document.rejection_reason = "too_short"
            stats.rejected += 1
            continue

        try:
            result = await llm.analyze(
                kind=document.kind, title=document.title, text=text, url=document.url
            )
        except LlmError as exc:
            document.status = "failed"
            document.rejection_reason = "llm_error"
            stats.failed += 1
            log.warning("llm.failed", document_id=document.id, error=str(exc)[:200])
            continue
        except Exception as exc:
            document.status = "failed"
            document.rejection_reason = "provider_error"
            stats.failed += 1
            log.warning("llm.unexpected", document_id=document.id, error=str(exc)[:200])
            continue

        data = result.data
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
            tags=data.tags,
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

        vector = embedder.embed(
            embedding_text(data.summary_zh, data.summary_en, data.tags, document.title)
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
