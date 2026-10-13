"""实体别名裁决：用判官给启发式候选做裁决。

两段式：
1. **召回**（沿用 find_alias_candidates）：跨书写系统 + 文档重合度 + 频次量级，
   成本低、只求召回、宁可漏报；
2. **裁决**（本模块）：用判官对每个候选判「是否同一实体」，给出可路由的分数。

路由由代码决定，不由模型决定（cookbook 架构模式）：
- 分数 >= merge 阈值 -> 自动合并；
- 中间地带 -> 进管理台人工队列（带模型建议，降低人工判断成本）；
- 明确否 -> 记为否决，避免下次重复提问。

阈值来自实测，不是拍的：
app/eval/alignment.py 在**人工别名表**（31 组 / 274 对 / 人工标注）上实测，
锁定测试集 AUC 0.796、F1 0.882，校准集选出的最优阈值是 0.406。
注意它远低于量表名义中点 1.5——判官几乎不使用最高档位（实测档位 2 从不出现），
所以任何写死的「中点阈值」都会让召回率掉到接近 0。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.alignment import alignment_question, build_prompt
from app.judgement import JudgementClient, JudgementError, get_judgement_client
from app.pipeline.aliases import find_alias_candidates

log = structlog.get_logger("pipeline.alias_adjudication")

# 实测最优阈值（见模块文档）；可用配置覆盖，但默认值有实证依据
DEFAULT_MERGE_THRESHOLD = 0.406
DEFAULT_REVIEW_FLOOR = 0.2


@dataclass(slots=True)
class Adjudication:
    """对一对候选实体的裁决结果。"""

    kind: str
    left_id: int
    left_name: str
    right_id: int
    right_name: str
    score: float
    confidence: float | None
    verdict: str  # merge / review / reject
    shared_documents: int = 0
    jaccard: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "left": {"id": self.left_id, "name": self.left_name},
            "right": {"id": self.right_id, "name": self.right_name},
            "score": round(self.score, 4),
            "confidence": self.confidence,
            "verdict": self.verdict,
            "shared_documents": self.shared_documents,
            "jaccard": self.jaccard,
        }


@dataclass(slots=True)
class AdjudicationReport:
    candidates: int = 0
    merged: int = 0
    review: int = 0
    rejected: int = 0
    failed: int = 0
    provider: str = ""
    model: str = ""
    threshold: float = DEFAULT_MERGE_THRESHOLD
    results: list[Adjudication] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "candidates": self.candidates,
            "merged": self.merged,
            "review": self.review,
            "rejected": self.rejected,
            "failed": self.failed,
            "provider": self.provider,
            "model": self.model,
            "threshold": self.threshold,
            "results": [item.as_dict() for item in self.results],
            "errors": self.errors[:20],
        }


def route_verdict(
    score: float,
    *,
    merge_threshold: float = DEFAULT_MERGE_THRESHOLD,
    review_floor: float = DEFAULT_REVIEW_FLOOR,
) -> str:
    """代码掌权：把分数映射成动作（纯函数，便于单测）。"""
    if score >= merge_threshold:
        return "merge"
    if score >= review_floor:
        return "review"
    return "reject"


async def adjudicate_candidates(
    session: AsyncSession,
    *,
    limit: int = 30,
    min_shared_docs: int = 2,
    merge_threshold: float = DEFAULT_MERGE_THRESHOLD,
    client: JudgementClient | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> AdjudicationReport:
    """对启发式候选逐个裁决。单对失败不影响其它。"""
    judge = client or get_judgement_client()
    if judge is None:
        raise JudgementError("未配置判官（JUDGEMENT_PROVIDER=none），无法裁决")

    pairs = candidates
    if pairs is None:
        pairs = await find_alias_candidates(session, min_shared_docs=min_shared_docs, limit=limit)

    report = AdjudicationReport(
        candidates=len(pairs), provider=judge.provider, threshold=merge_threshold
    )
    question = alignment_question()
    for candidate in pairs:
        left = candidate.get("left") or {}
        right = candidate.get("right") or {}
        left_name = str(left.get("name", ""))
        right_name = str(right.get("name", ""))
        try:
            response = await judge.ask(
                build_prompt(_as_pair(left_name, right_name)), {"same_entity": question}
            )
        except JudgementError as exc:
            report.failed += 1
            report.errors.append(f"{left_name} ~ {right_name}: {str(exc)[:100]}")
            continue

        report.model = response.model or report.model
        answer = response.answers.get("same_entity")
        if answer is None:
            report.failed += 1
            continue

        score = float(answer.score or 0.0)
        verdict = route_verdict(
            score, merge_threshold=merge_threshold, review_floor=DEFAULT_REVIEW_FLOOR
        )
        report.results.append(
            Adjudication(
                kind=str(candidate.get("kind", "")),
                left_id=int(left.get("id", 0)),
                left_name=left_name,
                right_id=int(right.get("id", 0)),
                right_name=right_name,
                score=score,
                confidence=answer.confidence,
                verdict=verdict,
                shared_documents=int(candidate.get("shared_documents", 0) or 0),
                jaccard=float(candidate.get("jaccard", 0.0) or 0.0),
            )
        )
        if verdict == "merge":
            report.merged += 1
        elif verdict == "review":
            report.review += 1
        else:
            report.rejected += 1
    return report


if TYPE_CHECKING:
    from app.eval.alignment import Pair


def _as_pair(left: str, right: str) -> Pair:
    """构造 Pair；放在函数内导入以避免与 eval 模块的循环依赖。"""
    from app.eval.alignment import Pair

    return Pair(left=left, right=right, label=False)


def pairs_to_merge(report: AdjudicationReport) -> list[dict[str, Any]]:
    """把 merge 结论转成管理台批量合并接口需要的格式。

    只信 verdict，**不要**再用 decide() 二次过滤：
    decide() 用的是量表中点阈值（1.5），而 route_verdict() 用的是实测阈值（0.406）。
    二次过滤会让刚刚被路由器批准、但分数低于 1.5 的合并被静默丢掉——
    实测那会是绝大多数（判官几乎不使用最高档位）。
    """
    return [
        {
            "kind": item.kind,
            "canonical_id": item.left_id,
            "alias_ids": [item.right_id],
            "score": item.score,
        }
        for item in report.results
        if item.verdict == "merge"
    ]
