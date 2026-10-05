"""实体别名：人工别名表 → 自动合并 + 候选发现。

为什么随应用发布而不是放 infra/seed：别名表是**应用知识**（决定展示出来的实体是谁），
必须随镜像一起发布；`infra/seed` 放的是环境相关的种子数据（数据源清单）。

注意：**不要放进 app/data/**——仓库 .gitignore 里的 `data/` 是给运行期数据目录的，
别名表放进去会被静默漏提交（v1 就是这么被 CI 抓出来的）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.entity import Entity, EntityMention
from app.pipeline.entities import entity_key

DEFAULT_ALIAS_FILE = Path(__file__).resolve().parents[1] / "entity_aliases.yaml"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class AliasGroup:
    canonical: str
    kind: str
    aliases: tuple[str, ...]

    @property
    def canonical_key(self) -> str:
        return entity_key(self.kind, self.canonical)

    def member_keys(self) -> list[str]:
        return [entity_key(self.kind, name) for name in (self.canonical, *self.aliases)]


def alias_file_path() -> Path:
    import os

    override = os.environ.get("ENTITY_ALIAS_FILE", "").strip()
    return Path(override) if override else DEFAULT_ALIAS_FILE


def load_alias_groups(path: Path | None = None) -> list[AliasGroup]:
    """读取别名表；文件缺失时返回空表并保持可用（不阻断采集/处理）。"""
    import yaml  # type: ignore[import-untyped]

    target = path or alias_file_path()
    if not target.is_file():
        return []
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    groups: list[AliasGroup] = []
    for item in payload.get("groups") or []:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical") or "").strip()
        kind = str(item.get("kind") or "org").strip().lower()
        aliases = tuple(
            str(name).strip() for name in (item.get("aliases") or []) if str(name).strip()
        )
        if canonical and aliases:
            groups.append(AliasGroup(canonical=canonical, kind=kind, aliases=aliases))
    return groups


@lru_cache(maxsize=4)
def _index_for(path_str: str) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for group in load_alias_groups(Path(path_str)):
        canonical_key = group.canonical_key
        for key in group.member_keys():
            index[key] = (canonical_key, group.canonical)
    return index


def refresh_alias_index() -> None:
    """别名表被改写后调用（管理台确认候选会写文件，缓存必须失效）。"""
    _index_for.cache_clear()


def resolve_alias(kind: str, name: str) -> tuple[str, str]:
    """返回 (规范 key, 规范名)；没有匹配规则时返回自身。"""
    index = _index_for(str(alias_file_path()))
    key = entity_key(kind, name)
    return index.get(key, (key, name.strip()[:200]))


async def apply_alias_groups(session: AsyncSession, groups: list[AliasGroup]) -> dict[str, int]:
    """把别名实体并入规范实体：搬提及、重算计数、保留别名行用于审计。"""
    stats = {"groups": 0, "merged": 0, "promoted": 0, "moved": 0, "dropped": 0, "missing": 0}
    for group in groups:
        stats["groups"] += 1
        members = (
            (await session.execute(select(Entity).where(Entity.key.in_(group.member_keys()))))
            .scalars()
            .all()
        )
        if not members:
            stats["missing"] += 1
            continue

        canonical = next((item for item in members if item.key == group.canonical_key), None)
        if canonical is None:
            # 规范实体还不存在：把已有成员提升为规范实体（改 key 与展示名）
            canonical = members[0]
            canonical.key = group.canonical_key
            canonical.name = group.canonical
            stats["promoted"] += 1

        existing_docs = set(
            (
                await session.execute(
                    select(EntityMention.document_id).where(EntityMention.entity_id == canonical.id)
                )
            )
            .scalars()
            .all()
        )
        for member in members:
            if member.id == canonical.id:
                continue
            mentions = (
                (
                    await session.execute(
                        select(EntityMention).where(EntityMention.entity_id == member.id)
                    )
                )
                .scalars()
                .all()
            )
            for mention in mentions:
                if mention.document_id in existing_docs:
                    # 同一文档里两种写法都出现过：只保留一条
                    await session.delete(mention)
                    stats["dropped"] += 1
                else:
                    mention.entity_id = canonical.id
                    existing_docs.add(mention.document_id)
                    stats["moved"] += 1
            member.canonical_entity_id = canonical.id
            member.mention_count = 0
            stats["merged"] += 1

        await session.flush()
        total = (
            await session.execute(
                select(func.count())
                .select_from(EntityMention)
                .where(EntityMention.entity_id == canonical.id)
            )
        ).scalar_one()
        canonical.mention_count = int(total or 0)
        merged_names = [member.name for member in members if member.id != canonical.id]
        canonical.aliases = sorted({*list(canonical.aliases or []), *merged_names})
        canonical.canonical_entity_id = None
    await session.flush()
    return stats


def is_cjk(name: str) -> bool:
    return bool(_CJK_RE.search(name or ""))


async def find_alias_candidates(
    session: AsyncSession,
    *,
    min_shared_docs: int = 2,
    min_jaccard: float = 0.5,
    max_ratio: float = 3.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """找"疑似同一实体"的候选对：同类型 + 跨书写系统 + 文档重合度高。

    只用共现是不够的（特朗普 与 习近平 也会同框 7 次），所以加了 Jaccard 重合度与频次量级约束，
    目的仍是"宁可漏报，不要给人工一堆噪音"。
    """
    left = aliased(Entity)
    right = aliased(Entity)
    left_mention = aliased(EntityMention)
    right_mention = aliased(EntityMention)
    shared = func.count(func.distinct(left_mention.document_id))
    left_total = (
        select(func.count())
        .select_from(EntityMention)
        .where(EntityMention.entity_id == left.id)
        .scalar_subquery()
    )
    right_total = (
        select(func.count())
        .select_from(EntityMention)
        .where(EntityMention.entity_id == right.id)
        .scalar_subquery()
    )
    stmt = (
        select(
            left.id,
            left.name,
            left.kind,
            right.id,
            right.name,
            shared.label("shared"),
            left_total.label("left_total"),
            right_total.label("right_total"),
        )
        .join(left_mention, left_mention.entity_id == left.id)
        .join(right_mention, right_mention.document_id == left_mention.document_id)
        .join(right, right.id == right_mention.entity_id)
        .where(left.kind == right.kind)
        .where(left.id < right.id)
        .where(left.canonical_entity_id.is_(None))
        .where(right.canonical_entity_id.is_(None))
        .group_by(left.id, left.name, left.kind, right.id, right.name)
        .having(shared >= min_shared_docs)
        .order_by(shared.desc())
        .limit(limit * 4)
    )
    rows = (await session.execute(stmt)).all()
    candidates: list[dict[str, Any]] = []
    for left_id, left_name, kind, right_id, right_name, count, left_n, right_n in rows:
        if is_cjk(left_name) == is_cjk(right_name):
            # 只把"跨书写系统"的对子当候选，避免把同语言的两个不同实体误报
            continue
        left_n = int(left_n or 0)
        right_n = int(right_n or 0)
        shared_n = int(count)
        union = left_n + right_n - shared_n
        jaccard = (shared_n / union) if union > 0 else 0.0
        # 同一个实体的两种写法几乎总在同一批文档里出现；而"相关的两个实体"（特朗普 vs 习近平）
        # 只是偶尔同框。因此要求：并集重合度高，且两边出现频次量级相近。
        if jaccard < min_jaccard:
            continue
        ratio = max(left_n, right_n) / max(min(left_n, right_n), 1)
        if ratio > max_ratio:
            continue
        candidates.append(
            {
                "kind": kind,
                "left": {"id": int(left_id), "name": left_name, "mentions": left_n},
                "right": {"id": int(right_id), "name": right_name, "mentions": right_n},
                "shared_documents": shared_n,
                "jaccard": round(jaccard, 3),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates
