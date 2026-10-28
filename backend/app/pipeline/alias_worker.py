"""实体别名自动发现 Worker：定时运行裁决并将结果路由到自动合并或审核队列。"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.entity import AliasReview
from app.pipeline.alias_adjudication import adjudicate_candidates
from app.pipeline.aliases import AliasGroup, apply_alias_groups

log = structlog.get_logger("pipeline.alias_worker")


async def run_alias_discovery(session: AsyncSession) -> None:
    """
    执行一次全量别名发现流程：
    1. 召回候选 $\rightarrow$ 2. 判官裁决 $\rightarrow$ 3. 路由动作
    """
    settings = get_settings()

    try:
        # 1. & 2. 召回与裁决
        # 每次跑少量候选以避免 LLM 成本过高
        report = await adjudicate_candidates(
            session, limit=50, merge_threshold=settings.alias_auto_merge_confidence
        )

        log.info(
            "alias.discovery.report",
            candidates=report.candidates,
            merged=report.merged,
            review=report.review,
        )

        # 3. 路由动作
        # A. 自动合并
        if report.merged > 0:
            # 构造 AliasGroup 列表
            groups: list[AliasGroup] = []
            for res in report.results:
                if res.verdict == "merge":
                    groups.append(
                        AliasGroup(
                            canonical=res.left_name, kind=res.kind, aliases=(res.right_name,)
                        )
                    )

            stats = await apply_alias_groups(session, groups)
            log.info("alias.auto_merge.stats", **stats)

        # B. 进入审核队列
        review_count = 0
        for res in report.results:
            if res.verdict == "review":
                # 检查是否已在队列中
                # (此处简化实现，直接插入)
                review = AliasReview(
                    kind=res.kind,
                    left_id=res.left_id,
                    right_id=res.right_id,
                    left_name=res.left_name,
                    right_name=res.right_name,
                    score=res.score,
                    confidence=res.confidence,
                    shared_documents=res.shared_documents,
                    jaccard=res.jaccard,
                )
                session.add(review)
                review_count += 1

        if review_count > 0:
            await session.flush()
            log.info("alias.review_queued", count=review_count)

    except Exception as exc:
        log.exception("alias.discovery.failed", error=str(exc))
