"""采集入库：归一化 + SimHash 前置去重（在调用 LLM 之前省 token）。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import RawItem
from app.config import get_settings
from app.models.document import Document
from app.models.source import Source
from app.pipeline import normalize, simhash

# 参与 SimHash 比对的近期文档窗口（Phase 1 在 Python 内比对；
# 数据量上去后改用 pg 位的 popcount 或专门索引）
SIMHASH_WINDOW_DAYS = 3
SIMHASH_CANDIDATES_LIMIT = 5000


@dataclass(slots=True)
class IngestStats:
    seen: int = 0
    new: int = 0
    duplicate_url: int = 0
    near_duplicate: int = 0
    invalid: int = 0
    too_old: int = 0
    new_document_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "seen": self.seen,
            "new": self.new,
            "duplicate_url": self.duplicate_url,
            "near_duplicate": self.near_duplicate,
            "invalid": self.invalid,
            "too_old": self.too_old,
        }


def is_too_old(published_at: datetime | None, *, now: datetime, max_age_days: int) -> bool:
    """发布时间早于阈值的内容不进 Feed（发布信息缺失时无法判断，按不旧处理）。"""
    if published_at is None:
        return False
    return now - published_at > timedelta(days=max_age_days)


async def _recent_simhashes(session: AsyncSession) -> list[tuple[int, int]]:
    since = datetime.now(UTC) - timedelta(days=SIMHASH_WINDOW_DAYS)
    stmt = (
        select(Document.id, Document.simhash)
        .where(Document.simhash.is_not(None))
        .where(Document.fetched_at >= since)
        .order_by(Document.id.desc())
        .limit(SIMHASH_CANDIDATES_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    return [
        (int(doc_id), simhash.from_signed64(int(value)))
        for doc_id, value in rows
        if value is not None
    ]


async def ingest_items(
    session: AsyncSession,
    *,
    source: Source | None,
    fetch_run_id: int | None,
    items: Iterable[RawItem],
) -> IngestStats:
    """把一批 RawItem 规范化入库；重复项也落库（status=deduped）以便审计。"""
    settings = get_settings()
    stats = IngestStats()
    candidates = await _recent_simhashes(session)
    seen_urls: set[str] = set()

    for item in items:
        stats.seen += 1
        canonical = normalize.canonicalize_url(item.url)
        title = normalize.strip_html(item.title)
        if not canonical or not title:
            stats.invalid += 1
            continue

        existing = (
            await session.execute(select(Document.id).where(Document.canonical_url == canonical))
        ).scalar_one_or_none()
        if existing is not None or canonical in seen_urls:
            stats.duplicate_url += 1
            continue
        seen_urls.add(canonical)

        excerpt = normalize.excerpt_of(item.summary)
        published_at = normalize.to_utc(item.published_at)
        too_old = is_too_old(
            published_at,
            now=datetime.now(UTC),
            max_age_days=settings.max_item_age_days,
        )
        fingerprint = simhash.simhash64(f"{title} {excerpt}")
        near_dup_of: int | None = None
        for doc_id, other in candidates:
            if simhash.is_near_duplicate(fingerprint, other, settings.simhash_hamming_threshold):
                near_dup_of = doc_id
                break

        if near_dup_of is not None:
            status = "deduped"
            rejection_reason: str | None = f"simhash:{near_dup_of}"
        elif too_old:
            status = "rejected"
            rejection_reason = "too_old"
        else:
            status = "pending"
            rejection_reason = None

        document = Document(
            source_id=source.id if source else None,
            fetch_run_id=fetch_run_id,
            url=item.url.strip(),
            canonical_url=canonical,
            title=title[:512],
            author=(item.author or None) and item.author[:200],
            published_at=published_at,
            language=item.language or normalize.detect_language(f"{title} {excerpt}"),
            kind=item.kind or "news",
            excerpt=excerpt or None,
            content_hash=normalize.content_hash(title, excerpt),
            simhash=simhash.to_signed64(fingerprint),
            status=status,
            rejection_reason=rejection_reason,
        )
        session.add(document)
        await session.flush()
        stats.new_document_ids.append(document.id)

        if near_dup_of is not None:
            stats.near_duplicate += 1
        elif too_old:
            stats.too_old += 1
        else:
            stats.new += 1
            candidates.append((document.id, fingerprint))

    await session.flush()
    return stats


def summarize(stats: IngestStats) -> dict[str, object]:
    return stats.as_dict()


__all__: Sequence[str] = ("IngestStats", "ingest_items", "summarize")
