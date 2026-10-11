"""评估门：判官在这些问题上到底有没有信息量。

设计要点（每一处都是为了不自己骗自己）：

1. **客观标签，零模型参与**。标签来自数据库里的事实：某实体在 T 之后 horizon 天内
   是否出现了新的报道。不用 LLM 打标签，所以不存在「用模型评模型」的循环。
2. **时间切割防泄漏**。state 只用 T 时刻已知的摘要；标签只看 T 之后。
3. **必须报基线**。基率 0.2 的二分类上，永远猜「不会发生」就有 0.8 准确率。
   真正要比的是 Brier 有没有打赢「常数预测基率」这个更强的基线。
4. **看概率质量，不只看 argmax**。Brier / ECE / 可靠性曲线 / 风险-覆盖一起看。

**这个门验证的是什么**：模型对「该事件未来是否还会有新进展」这个**客观子问题**的概率质量。
它是推演能力的必要非充分条件——escalation / downstream 这些语义判断**仍然未被验证**，
因为在当前语料上它们没有客观标签。报告里必须如实写出这条边界。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.metrics import (
    CalibrationBucket,
    CoveragePoint,
    Observation,
    accuracy,
    base_rate,
    brier_baseline,
    brier_score,
    brier_skill_score,
    expected_calibration_error,
    log_loss,
    majority_accuracy,
    reliability_curve,
    risk_coverage,
)
from app.judgement import JudgementClient, JudgementError, NoulQuestion, get_judgement_client

log = structlog.get_logger("eval.judgement")

# 通过门禁的最低要求（写死在代码里，避免"调参调到通过"）
MIN_SKILL = 0.05
MAX_ECE = 0.15
MAX_STATE_CHARS = 700

QUESTION_TEMPLATE = (
    "未来 {horizon} 天内，关于该事件是否会再出现可观察的新进展"
    "（新的官方表态、新的报道、事态变化）？"
)


@dataclass(slots=True)
class EvalCase:
    """一个可核对的历史样本。"""

    entity_id: int
    entity_name: str
    as_of: datetime
    state: str
    document_id: int


@dataclass(slots=True)
class EvalReport:
    provider: str
    model: str
    horizon_days: int
    sample_size: int
    base_rate: float
    brier: float
    brier_baseline: float
    skill: float
    accuracy: float
    majority_accuracy: float
    log_loss: float
    ece: float
    reliability: list[CalibrationBucket] = field(default_factory=list)
    risk_coverage: list[CoveragePoint] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    failures: int = 0
    latency_seconds: float = 0.0
    input_tokens: int = 0
    passed: bool = False
    verdict: str = ""
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "horizon_days": self.horizon_days,
            "sample_size": self.sample_size,
            "base_rate": self.base_rate,
            "brier": self.brier,
            "brier_baseline": self.brier_baseline,
            "brier_skill_score": self.skill,
            "accuracy": self.accuracy,
            "majority_accuracy": self.majority_accuracy,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "failures": self.failures,
            "latency_seconds": self.latency_seconds,
            "input_tokens": self.input_tokens,
            "passed": self.passed,
            "verdict": self.verdict,
            "limitations": self.limitations,
            "reliability": [
                {
                    "range": f"{bucket.lower:.2f}-{bucket.upper:.2f}",
                    "count": bucket.count,
                    "mean_probability": bucket.mean_probability,
                    "empirical_rate": bucket.empirical_rate,
                }
                for bucket in self.reliability
            ],
            "risk_coverage": [
                {
                    "coverage": point.coverage,
                    "accuracy": point.accuracy,
                    "mean_decisiveness": point.mean_decisiveness,
                }
                for point in self.risk_coverage
            ],
        }


async def select_cases(
    session: AsyncSession,
    *,
    horizon_days: int,
    limit: int,
    min_mention_count: int = 2,
    order: str = "random",
) -> list[EvalCase]:
    """挑样本：实体首次出现为 T，且 T + horizon 仍在语料范围内（窗口完整）。

    order 决定取样方式，**这个选择会显著改变结论**：
    - random（默认）：全体实体的近似均匀抽样。2026-10 语料上 7 天基率约 0.20，
      是一个不平凡的二分类题，适合当门禁；
    - prominent：按提及数取最显眼的实体。它们几乎必然被持续报道（实测基率 0.95），
      基线变得极强（常数预测就有 Brier 0.05），是另一种（更难的）检验。

    默认用 random：门禁要回答的是「概率本身有没有信息量」，而不是
    「能不能猜中头部实体的常识」。两种都跑一遍更有说服力。
    """
    # md5(id) 排序 = 稳定但近似随机的顺序（不用数据库 random()，保证可复现）
    ordering = "e.mention_count desc, e.id" if order == "prominent" else "md5(e.id::text), e.id"
    rows = (
        await session.execute(
            text(
                f"""
                with first_seen as (
                  select em.entity_id, min(d.published_at) as t0
                  from entity_mentions em
                  join documents d on d.id = em.document_id
                  where d.published_at is not null
                  group by em.entity_id
                ),
                corpus as (select max(published_at) as tmax from documents)
                select e.id, e.name, fs.t0
                from first_seen fs
                join entities e on e.id = fs.entity_id
                cross join corpus
                where e.mention_count >= :min_mentions
                  and fs.t0 + make_interval(days => :horizon) <= corpus.tmax
                order by {ordering}
                limit :limit
                """
            ),
            {"min_mentions": min_mention_count, "horizon": horizon_days, "limit": limit},
        )
    ).all()

    cases: list[EvalCase] = []
    for entity_id, name, as_of in rows:
        state = await _build_state(session, entity_id, as_of)
        if not state:
            continue
        document_id = (
            await session.execute(
                text(
                    """
                    select d.id from entity_mentions em
                    join documents d on d.id = em.document_id
                    where em.entity_id = :entity_id and d.published_at = :as_of
                    order by d.id limit 1
                    """
                ),
                {"entity_id": entity_id, "as_of": as_of},
            )
        ).scalar()
        if document_id is None:
            continue
        cases.append(
            EvalCase(
                entity_id=int(entity_id),
                entity_name=str(name),
                as_of=as_of,
                state=state,
                document_id=int(document_id),
            )
        )
    return cases


async def _build_state(session: AsyncSession, entity_id: int, as_of: datetime) -> str:
    """只用 T 时刻（含）已知的摘要拼 state，防止未来信息泄漏。"""
    rows = (
        await session.execute(
            text(
                """
                select d.title, a.summary_zh, a.summary_en
                from entity_mentions em
                join documents d on d.id = em.document_id
                left join analyses a on a.document_id = d.id
                where em.entity_id = :entity_id and d.published_at <= :as_of
                order by d.published_at desc, d.id desc
                limit 5
                """
            ),
            {"entity_id": entity_id, "as_of": as_of},
        )
    ).all()
    blocks: list[str] = []
    for title, summary_zh, summary_en in rows:
        if title:
            blocks.append(f"标题：{title}")
        if summary_zh:
            blocks.append(f"摘要：{summary_zh}")
        elif summary_en:
            blocks.append(f"Summary: {summary_en}")
        if sum(len(block) for block in blocks) >= MAX_STATE_CHARS:
            break
    return "\n".join(blocks)[:MAX_STATE_CHARS]


async def _label(session: AsyncSession, case: EvalCase, horizon_days: int) -> bool:
    """客观标签：T 之后 horizon 天内该实体是否出现了新的报道。"""
    count = (
        await session.execute(
            text(
                """
                select count(*)
                from entity_mentions em
                join documents d on d.id = em.document_id
                where em.entity_id = :entity_id
                  and d.published_at > :as_of
                  and d.published_at <= :until
                """
            ),
            {
                "entity_id": case.entity_id,
                "as_of": case.as_of,
                "until": case.as_of + timedelta(days=horizon_days),
            },
        )
    ).scalar()
    return bool(count and int(count) > 0)


async def run_evaluation(
    session: AsyncSession,
    *,
    horizon_days: int = 7,
    sample: int = 200,
    order: str = "random",
    client: JudgementClient | None = None,
) -> EvalReport:
    """跑完整评估：取样本 → 逐条问判官 → 与客观标签比对 → 汇总指标。"""
    import time

    judge = client or get_judgement_client()
    if judge is None:
        raise JudgementError("未配置判官（JUDGEMENT_PROVIDER=none），无法评估")

    cases = await select_cases(session, horizon_days=horizon_days, limit=sample, order=order)
    if not cases:
        raise JudgementError(f"在 {horizon_days} 天 horizon 下没有可用样本（语料跨度太短）")

    question = NoulQuestion(instructions=QUESTION_TEMPLATE.format(horizon=horizon_days))
    observations: list[Observation] = []
    failures = 0
    tokens = 0
    started = time.time()
    model_name = ""

    for case in cases:
        try:
            response = await judge.ask(case.state, {"progress": question})
        except JudgementError as exc:
            failures += 1
            log.warning("eval.case_failed", entity_id=case.entity_id, error=str(exc)[:150])
            continue
        answer = response.answers.get("progress")
        if answer is None or answer.noul is None:
            failures += 1
            continue
        model_name = response.model or model_name
        tokens += response.input_tokens
        outcome = await _label(session, case, horizon_days)
        observations.append(
            Observation(
                key=f"entity:{case.entity_id}",
                probability=round(float(answer.noul), 4),
                outcome=outcome,
                note=case.entity_name,
            )
        )

    if not observations:
        raise JudgementError(f"所有 {len(cases)} 个样本都失败了，无法评估")

    elapsed = time.time() - started
    report = EvalReport(
        provider=judge.provider,
        model=model_name,
        horizon_days=horizon_days,
        sample_size=len(observations),
        base_rate=round(base_rate(observations), 4),
        brier=round(brier_score(observations), 4),
        brier_baseline=round(brier_baseline(observations), 4),
        skill=round(brier_skill_score(observations), 4),
        accuracy=round(accuracy(observations), 4),
        majority_accuracy=round(majority_accuracy(observations), 4),
        log_loss=round(log_loss(observations), 4),
        ece=round(expected_calibration_error(observations), 4),
        reliability=reliability_curve(observations),
        risk_coverage=risk_coverage(observations),
        observations=observations,
        failures=failures,
        latency_seconds=round(elapsed, 1),
        input_tokens=tokens,
    )
    report.limitations = [
        "标签是客观的（T 之后是否出现新报道），但只覆盖「事件是否还在发展」这一子问题；",
        "escalation / downstream / second_order 这些语义判断在当前语料上没有客观标签，仍未验证；",
        "语料跨度约 33 天，horizon 上限约 10 天，长周期推演无法用现有数据检验；",
        "标签来源是自有采集语料，只反映「被我们采到的媒体是否继续报道」，存在采集偏差。",
    ]
    threshold_note = f"门槛：Brier 技能分 > {MIN_SKILL} 且 ECE < {MAX_ECE}"
    if report.skill > MIN_SKILL and report.ece < MAX_ECE:
        report.passed = True
        report.verdict = f"通过评估门（{threshold_note}）：概率有信息量且校准可接受"
    else:
        report.passed = False
        report.verdict = (
            f"未通过评估门（{threshold_note}）："
            f"实际 skill={report.skill}, ECE={report.ece}。"
            "推演输出必须继续标注「未经校准」，不得当作预测发布"
        )
    return report
