"""实体归一与提及写入。"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.entity import Entity, EntityMention

_WS_RE = re.compile(r"[\s\u3000]+")
_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff ]+")
# 中文之间的空格视为噪声（模型偶尔输出「中国 政府」），英文单词之间的空格保留
_CJK_GAP_RE = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")


def normalize_entity_name(name: str) -> str:
    """归一化实体名：NFKC → 小写 → 去标点 → 压空白。

    只做同形归一（大小写、全半角、标点差异），不做跨语言别名合并。
    """
    text = unicodedata.normalize("NFKC", name or "").lower()
    text = _WS_RE.sub(" ", text)
    text = _CJK_GAP_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    return text.strip()[:200]


def entity_key(kind: str, name: str) -> str:
    normalized = normalize_entity_name(name)
    return f"{(kind or 'org').strip().lower()[:16]}:{normalized}"[:300]


def dedupe_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一文档内同名实体只保留 salience 最高的那条（模型偶尔重复输出）。"""
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or not normalize_entity_name(name):
            continue
        kind = str(item.get("kind") or "org")
        key = entity_key(kind, name)
        current = best.get(key)
        if current is None or float(item.get("salience") or 0) > float(
            current.get("salience") or 0
        ):
            best[key] = item
    return list(best.values())


async def upsert_entities(
    session: AsyncSession,
    *,
    document: Document,
    analysis_id: int | None,
    entities: list[dict[str, Any]],
) -> int:
    """写入实体与提及，返回处理条数；同一文档的同一实体不会重复计。"""
    now = datetime.now(UTC)
    written = 0
    # 延迟导入：aliases 依赖本模块的 entity_key，顶层互相导入会成环
    from app.pipeline.aliases import resolve_alias

    for item in dedupe_entities(entities):
        raw_name = str(item["name"]).strip()[:200]
        kind = str(item.get("kind") or "org")[:16]
        # 命中别名表时直接落到规范实体，否则每轮处理都会把时间线重新拆开
        key, display_name = resolve_alias(kind, raw_name)
        is_alias = raw_name != display_name

        entity = (
            await session.execute(select(Entity).where(Entity.key == key))
        ).scalar_one_or_none()
        if entity is None:
            entity = Entity(
                key=key,
                name=display_name,
                kind=kind,
                aliases=[],
                mention_count=0,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(entity)
            await session.flush()
        recorded = list(entity.aliases or [])
        if is_alias and raw_name not in recorded:
            entity.aliases = [*recorded, raw_name]

        exists = (
            await session.execute(
                select(EntityMention.id)
                .where(EntityMention.entity_id == entity.id)
                .where(EntityMention.document_id == document.id)
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                EntityMention(
                    entity_id=entity.id,
                    document_id=document.id,
                    analysis_id=analysis_id,
                    salience=float(item.get("salience") or 0),
                )
            )
            entity.mention_count = (entity.mention_count or 0) + 1
        entity.last_seen_at = now
        written += 1
    await session.flush()
    return written
