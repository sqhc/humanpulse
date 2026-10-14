"""管理接口：手动触发作业、查看采集与用量、确认实体别名候选。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.db import get_session
from app.judgement import JudgementError
from app.models.document import FetchRun
from app.models.entity import Entity
from app.models.ops import LlmUsageDay
from app.models.source import Source
from app.pipeline.alias_adjudication import adjudicate_candidates
from app.pipeline.alias_table import (
    EntityRef,
    groups_from_merges,
    merge_into_table,
    validate_alias_file,
    write_alias_groups,
)
from app.pipeline.aliases import (
    apply_alias_groups,
    find_alias_candidates,
    load_alias_groups,
    refresh_alias_index,
)
from app.predictions import resolve_due
from app.schemas.admin import (
    EntityAliasApplyIn,
    EntityAliasApplyOut,
    EntityCandidateListOut,
    EntityCandidateOut,
    EntityCandidateSide,
)
from app.schemas.content import FetchRunOut, JobResultOut, LlmUsageOut
from app.workers.jobs import collect_all, run_brief, run_process

router = APIRouter(prefix="/admin")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/jobs/{job_name}/run", response_model=JobResultOut, summary="手动触发作业（管理员）")
async def run_job(
    job_name: Literal["collect", "process", "brief", "resolve-predictions"],
    session: SessionDep,
    _admin: AdminDep,
    force: Annotated[bool, Query(description="忽略 cadence 立即采集")] = False,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    kind: Annotated[Literal["daily", "weekly"], Query()] = "daily",
) -> JobResultOut:
    stats: dict[str, object]
    if job_name == "collect":
        stats = (await collect_all(session, force=force)).model_dump()
    elif job_name == "process":
        stats = (await run_process(session, limit=limit)).model_dump()
    elif job_name == "resolve-predictions":
        # 核对到期预测：需要判官（JUDGEMENT_PROVIDER != none）
        stats = (await resolve_due(session, limit=limit or 50)).as_dict()
    else:
        stats = await run_brief(session, kind=kind, force=force)
    return JobResultOut(job=job_name, stats=stats)


@router.get("/runs", response_model=list[FetchRunOut], summary="最近的采集批次（管理员）")
async def list_runs(
    session: SessionDep,
    _admin: AdminDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
) -> list[FetchRunOut]:
    rows = (
        await session.execute(
            select(FetchRun, Source.name)
            .outerjoin(Source, Source.id == FetchRun.source_id)
            .order_by(FetchRun.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        FetchRunOut(
            id=run.id,
            source_id=run.source_id,
            source_name=name,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            items_seen=run.items_seen,
            items_new=run.items_new,
            items_rejected=run.items_rejected,
            error=run.error,
        )
        for run, name in rows
    ]


@router.get("/usage", response_model=list[LlmUsageOut], summary="LLM 用量与成本（管理员）")
async def list_usage(
    session: SessionDep,
    _admin: AdminDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> list[LlmUsageOut]:
    since = date.today() - timedelta(days=days)
    rows = (
        (
            await session.execute(
                select(LlmUsageDay)
                .where(LlmUsageDay.day >= since)
                .order_by(LlmUsageDay.day.desc(), LlmUsageDay.model.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        LlmUsageOut(
            day=row.day.isoformat(),
            provider=row.provider,
            model=row.model,
            calls=row.calls,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            cost_usd=float(row.cost_usd or 0),
        )
        for row in rows
    ]


@router.get(
    "/entity-candidates",
    response_model=EntityCandidateListOut,
    summary="疑似同一实体的候选对（管理员）",
)
async def list_entity_candidates(
    session: SessionDep,
    _admin: AdminDep,
    min_shared: Annotated[int, Query(ge=1, le=50)] = 2,
    min_jaccard: Annotated[float, Query(ge=0.0, le=1.0)] = 0.5,
    max_ratio: Annotated[float, Query(ge=1.0, le=100.0)] = 3.0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EntityCandidateListOut:
    """管理台「实体候选」用：列出可以确认合并的候选对。

    默认阈值（jaccard>=0.5、频次比<=3）是偏保守的设置：只用共现会把
    「特朗普 与 习近平」这种同框关系也报上来（见 ADR-0009 的实测数据）。
    """
    raw = await find_alias_candidates(
        session,
        min_shared_docs=min_shared,
        min_jaccard=min_jaccard,
        max_ratio=max_ratio,
        limit=limit,
    )
    # P2：用判官给候选打「模型建议 + 分数」（判官未配置/失败时 score/verdict 为 None）
    scores: dict[tuple[int, int], tuple[float, str, float | None]] = {}
    try:
        report = await adjudicate_candidates(session, candidates=raw)
        for adj in report.results:
            scores[(adj.left_id, adj.right_id)] = (adj.score, adj.verdict, adj.confidence)
    except JudgementError:
        pass

    groups = load_alias_groups()
    candidates: list[EntityCandidateOut] = []
    for item in raw:
        left = item["left"]
        right = item["right"]
        key = (int(left.get("id", 0)), int(right.get("id", 0)))
        score, verdict, confidence = scores.get(key, (None, None, None))
        candidates.append(
            EntityCandidateOut(
                kind=item["kind"],
                left=EntityCandidateSide(**left),
                right=EntityCandidateSide(**right),
                shared_documents=item["shared_documents"],
                jaccard=item["jaccard"],
                score=score,
                verdict=verdict,
                confidence=confidence,
            )
        )
    return EntityCandidateListOut(
        candidates=candidates,
        alias_group_count=len(groups),
        alias_problems=validate_alias_file(),
        scanned_pairs=len(raw),
    )


@router.post(
    "/entity-aliases/apply",
    response_model=EntityAliasApplyOut,
    summary="确认合并实体并（可选）写回别名表（管理员）",
)
async def apply_entity_aliases(
    payload: EntityAliasApplyIn,
    session: SessionDep,
    _admin: AdminDep,
) -> EntityAliasApplyOut:
    """管理台确认候选后调用。

    默认只改数据库（remember=false）；勾选记住才写回仓库里的 YAML。
    这样误点一次不会污染随包发布的别名表，也避免开发栈把别人的文件改了。
    """
    if not payload.merges:
        raise HTTPException(status_code=400, detail="没有要合并的实体")

    ids = {merge.canonical_id for merge in payload.merges}
    ids.update(alias_id for merge in payload.merges for alias_id in merge.alias_ids)
    rows = (await session.execute(select(Entity).where(Entity.id.in_(ids)))).scalars().all()
    refs = {
        entity.id: EntityRef(
            id=entity.id,
            name=entity.name,
            kind=entity.kind,
            aliases=tuple(entity.aliases or []),
        )
        for entity in rows
    }

    groups, errors = groups_from_merges([merge.model_dump() for merge in payload.merges], refs)
    if errors:
        raise HTTPException(status_code=400, detail=errors)
    if not groups:
        raise HTTPException(status_code=400, detail="没有可执行的合并")

    stats = await apply_alias_groups(session, groups)

    remembered = False
    target: str | None = None
    total_groups = len(load_alias_groups())
    if payload.remember:
        table = merge_into_table(load_alias_groups(), groups)
        path = write_alias_groups(table)
        refresh_alias_index()
        remembered = True
        target = str(path)
        total_groups = len(table)

    return EntityAliasApplyOut(
        applied_groups=len(groups),
        merged=stats["merged"],
        promoted=stats["promoted"],
        moved=stats["moved"],
        dropped=stats["dropped"],
        missing=stats["missing"],
        remembered=remembered,
        alias_file=target,
        total_groups=total_groups,
        problems=validate_alias_file(),
    )
