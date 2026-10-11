"""预测登记、到期核对与校准汇总。

闭环长这样：
  推演生成 → 把每个带概率的节点登记成一条预测（登记原始概率，不改写话术）
  → 到期后用同一判官问一次「该预测是否已兑现」→ 落库 hit/missed + Brier
  → 汇总成校准曲线，公开在页面上

为什么登记的是节点而不是整条链的结论：
每个节点有独立的概率与到期时间，可以分别核对。只有这样才分得清
「模型对二阶效应的判断差」还是「对先行指标的判断差」。

诚实性约束：
- 没有新证据时判 unresolved 而不是猜 missed（无证据不等于未发生）；
- unresolved 顺延有限次后置 expired，避免永远挂着；
- 校准汇总只统计已判定的（hit/missed），未判定的单独计数并展示。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefs.schema import ProjectionChain
from app.eval.metrics import (
    Observation,
    base_rate,
    brier_baseline,
    brier_score,
    expected_calibration_error,
    reliability_curve,
)
from app.judgement import JudgementClient, JudgementError, NoulQuestion, get_judgement_client
from app.models.prediction import Prediction

log = structlog.get_logger("predictions.registry")

# 判定阈值：留出中间地带给 unresolved，避免把「拿不准」硬掰成对或错
HIT_THRESHOLD = 0.8
MISS_THRESHOLD = 0.2
MAX_DEFERRALS = 3
EVIDENCE_LIMIT = 6

# 这些节点才登记成预测：事实节点概率恒为 1，登记它没有信息量
TRACKED_KINDS = {"effect", "second_order", "counter", "indicator", "horizon"}


@dataclass(slots=True)
class ResolveReport:
    checked: int = 0
    hit: int = 0
    missed: int = 0
    unresolved: int = 0
    expired: int = 0
    failed: int = 0
    details: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "hit": self.hit,
            "missed": self.missed,
            "unresolved": self.unresolved,
            "expired": self.expired,
            "failed": self.failed,
            "details": self.details,
        }


async def register_chain(
    session: AsyncSession,
    chain: ProjectionChain,
    *,
    brief_id: int | None,
    provider: str,
    model: str,
    horizon_days: int,
    registered_at: datetime | None = None,
) -> list[Prediction]:
    """把一条推演链路里可证伪的节点登记成预测。"""
    moment = registered_at or datetime.now(UTC)
    created: list[Prediction] = []
    for node in chain.nodes:
        if node.kind not in TRACKED_KINDS:
            continue
        if not node.statement_zh.strip():
            continue
        prediction = Prediction(
            brief_id=brief_id,
            document_id=chain.document_id,
            cluster_id=chain.cluster_id,
            hop=node.hop,
            question_key=node.kind,
            statement_zh=node.statement_zh,
            statement_en=node.statement_en,
            predicted_probability=Decimal(str(round(node.probability, 4))),
            confidence=(
                Decimal(str(round(node.confidence, 4))) if node.confidence is not None else None
            ),
            horizon_days=horizon_days,
            due_at=moment + timedelta(days=horizon_days),
            status="open",
            provider=provider,
            model=model,
            evidence={"registered_at": moment.isoformat(), "deferrals": 0},
        )
        session.add(prediction)
        created.append(prediction)
    if created:
        await session.flush()
    return created


async def due_predictions(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 50
) -> list[Prediction]:
    """取到期且仍待核对的预测。"""
    moment = now or datetime.now(UTC)
    result = await session.execute(
        select(Prediction)
        .where(Prediction.status == "open", Prediction.due_at <= moment)
        .order_by(Prediction.due_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def _window_evidence(session: AsyncSession, prediction: Prediction) -> list[dict[str, str]]:
    """找核对窗口内的新文档当证据。

    窗口取 [登记时间, 到期时间]。用登记时间而不是 due_at 减 horizon，
    因为顺延过的预测窗口会变长。
    """
    registered_raw = (prediction.evidence or {}).get("registered_at")
    try:
        registered = datetime.fromisoformat(str(registered_raw))
    except (TypeError, ValueError):
        registered = prediction.due_at - timedelta(days=prediction.horizon_days)

    if prediction.entity_id is not None:
        sql = text(
            """
            select d.title, a.summary_zh
            from entity_mentions em
            join documents d on d.id = em.document_id
            left join analyses a on a.document_id = d.id
            where em.entity_id = :entity_id
              and d.published_at > :since and d.published_at <= :until
            order by d.published_at desc
            limit :limit
            """
        )
        params = {
            "entity_id": prediction.entity_id,
            "since": registered,
            "until": prediction.due_at,
            "limit": EVIDENCE_LIMIT,
        }
    elif prediction.cluster_id is not None:
        sql = text(
            """
            select d.title, a.summary_zh
            from cluster_members cm
            join documents d on d.id = cm.document_id
            left join analyses a on a.document_id = d.id
            where cm.cluster_id = :cluster_id
              and d.published_at > :since and d.published_at <= :until
            order by d.published_at desc
            limit :limit
            """
        )
        params = {
            "cluster_id": prediction.cluster_id,
            "since": registered,
            "until": prediction.due_at,
            "limit": EVIDENCE_LIMIT,
        }
    else:
        return []

    rows = (await session.execute(sql, params)).all()
    evidence: list[dict[str, str]] = []
    for title, summary in rows:
        evidence.append({"title": str(title or ""), "summary": str(summary or "")})
    return evidence


def _resolve_question(statement: str) -> NoulQuestion:
    return NoulQuestion(
        instructions=(
            "下面有一条此前的推演，以及之后一段时间的相关报道。"
            "请判断这条推演是否已经被后来的事实兑现。"
            "推演内容：" + statement
        )
    )


async def resolve_due(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 50,
    client: JudgementClient | None = None,
) -> ResolveReport:
    """核对到期的预测：问判官「是否已兑现」，落库状态与 Brier。"""
    judge = client or get_judgement_client()
    if judge is None:
        raise JudgementError("未配置判官（JUDGEMENT_PROVIDER=none），无法核对预测")

    moment = now or datetime.now(UTC)
    report = ResolveReport()
    for prediction in await due_predictions(session, now=moment, limit=limit):
        report.checked += 1
        evidence = await _window_evidence(session, prediction)
        if not evidence:
            # 窗口内没有任何新报道：无证据，不能判成「未发生」
            _defer(prediction, moment, report, reason="窗口内没有新报道")
            continue

        lines = []
        for item in evidence:
            if not item["title"]:
                continue
            lines.append("标题：" + item["title"])
            if item["summary"]:
                lines.append("摘要：" + item["summary"])
        state = chr(10).join(lines)[:900]

        try:
            response = await judge.ask(
                state, {"realized": _resolve_question(prediction.statement_zh)}
            )
        except JudgementError as exc:
            report.failed += 1
            log.warning(
                "predictions.resolve_failed", prediction_id=prediction.id, error=str(exc)[:150]
            )
            continue

        answer = response.answers.get("realized")
        if answer is None or answer.noul is None:
            report.failed += 1
            continue

        probability = float(answer.noul)
        prediction.resolved_probability = Decimal(str(round(probability, 4)))
        prediction.model = response.model or prediction.model
        prediction.evidence = {
            **(prediction.evidence or {}),
            "documents": len(evidence),
            "resolved_by": response.model,
        }

        if probability >= HIT_THRESHOLD or probability <= MISS_THRESHOLD:
            outcome = probability >= HIT_THRESHOLD
            prediction.status = "hit" if outcome else "missed"
            prediction.resolved_at = moment
            predicted = float(prediction.predicted_probability)
            gap = predicted - (1.0 if outcome else 0.0)
            prediction.brier = Decimal(str(round(gap * gap, 5)))
            if outcome:
                report.hit += 1
            else:
                report.missed += 1
            report.details.append(
                {
                    "id": prediction.id,
                    "status": prediction.status,
                    "predicted": predicted,
                    "resolved": probability,
                    "brier": float(prediction.brier),
                }
            )
        else:
            _defer(prediction, moment, report, reason="概率落在中间地带")
    await session.flush()
    return report


def _defer(prediction: Prediction, moment: datetime, report: ResolveReport, *, reason: str) -> None:
    """顺延一次；超过上限就置 expired，不让它永远挂着。"""
    evidence = dict(prediction.evidence or {})
    deferrals = int(evidence.get("deferrals") or 0) + 1
    evidence["deferrals"] = deferrals
    evidence["last_defer_reason"] = reason
    prediction.evidence = evidence
    if deferrals > MAX_DEFERRALS:
        prediction.status = "expired"
        prediction.resolved_at = moment
        report.expired += 1
    else:
        prediction.due_at = moment + timedelta(days=prediction.horizon_days)
        report.unresolved += 1


async def calibration_summary(session: AsyncSession) -> dict[str, object]:
    """校准汇总：只统计已判定（hit/missed）的预测，未判定的单独计数。

    与离线评估（app/eval）用同一套评分函数，所以页面上的数字和 make eval-judgement
    的报告可比；两处口径不一致会让人不知道该信哪个。
    """
    rows = (
        await session.execute(
            text(
                """
                select id, predicted_probability, (status = 'hit') as outcome
                from predictions
                where status in ('hit', 'missed')
                order by id
                """
            )
        )
    ).all()
    counts = (
        await session.execute(text("select status, count(*) from predictions group by status"))
    ).all()

    observations = [
        Observation(
            key="prediction:" + str(row[0]), probability=float(row[1]), outcome=bool(row[2])
        )
        for row in rows
    ]
    by_status = {str(status): int(count) for status, count in counts}

    payload: dict[str, object] = {
        "by_status": by_status,
        "resolved": len(observations),
        "hits": sum(1 for item in observations if item.outcome),
        "misses": sum(1 for item in observations if not item.outcome),
    }
    if observations:
        payload.update(
            {
                "base_rate": round(base_rate(observations), 4),
                "brier": round(brier_score(observations), 4),
                "brier_baseline": round(brier_baseline(observations), 4),
                "ece": round(expected_calibration_error(observations), 4),
                "reliability": [
                    {
                        "range": f"{bucket.lower:.2f}-{bucket.upper:.2f}",
                        "count": bucket.count,
                        "mean_probability": bucket.mean_probability,
                        "empirical_rate": bucket.empirical_rate,
                    }
                    for bucket in reliability_curve(observations)
                ],
            }
        )
    else:
        payload["note"] = "还没有已判定的预测；到期核对任务每天跑一次"
    return payload


def tracked_kinds() -> Sequence[str]:
    """哪些节点会被登记（给测试与前端用）。"""
    return tuple(sorted(TRACKED_KINDS))
