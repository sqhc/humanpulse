"""问题措辞与校准的对照实验。

要回答的两个问题：
1. 之前把「新进展」理解成重大进展是不是措辞问题？（对照 coverage 与 progress 两种问法）
2. Platt 校准能不能修掉系统性偏低？

方法学约束（比结果重要）：
- 样本按**实体**一次性切分成校准集 / 锁定测试集，两种措辞共用同一套切分，可比；
- Platt 参数只在校准集上拟合，**测试集的数字才是结论**；
- 所有对照都写进报告，包括失败的——只报通过的那个就是 p-hacking。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.calibration import PlattParams, calibrate, fit_platt, split_by_key
from app.eval.judgement import MAX_STATE_CHARS, EvalCase, _label, select_cases
from app.eval.metrics import (
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
    roc_auc,
)
from app.judgement import JudgementClient, JudgementError, NoulQuestion, get_judgement_client

log = structlog.get_logger("eval.experiment")

# 两种措辞：coverage 直接对应客观标签的口径，progress 是原先生产里用的说法
VARIANTS: dict[str, str] = {
    "coverage": "未来 {horizon} 天内，关于该事件是否还会有新的相关报道出现？",
    "progress": (
        "未来 {horizon} 天内，关于该事件是否会再出现可观察的新进展"
        "（新的官方表态、新的报道、事态变化）？"
    ),
}


@dataclass(slots=True)
class Metrics:
    sample_size: int
    base_rate: float
    brier: float
    brier_baseline: float
    skill: float
    accuracy: float
    majority_accuracy: float
    log_loss: float
    ece: float
    auc: float

    def as_dict(self) -> dict[str, float]:
        return {
            "sample_size": self.sample_size,
            "base_rate": self.base_rate,
            "brier": self.brier,
            "brier_baseline": self.brier_baseline,
            "skill": self.skill,
            "accuracy": self.accuracy,
            "majority_accuracy": self.majority_accuracy,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "auc": self.auc,
        }


def summarize(observations: Sequence[Observation]) -> Metrics:
    return Metrics(
        sample_size=len(observations),
        base_rate=round(base_rate(observations), 4),
        brier=round(brier_score(observations), 4),
        brier_baseline=round(brier_baseline(observations), 4),
        skill=round(brier_skill_score(observations), 4),
        accuracy=round(accuracy(observations), 4),
        majority_accuracy=round(majority_accuracy(observations), 4),
        log_loss=round(log_loss(observations), 4),
        ece=round(expected_calibration_error(observations), 4),
        auc=round(roc_auc(observations), 4),
    )


@dataclass(slots=True)
class VariantResult:
    variant: str
    question: str
    raw_test: Metrics
    calibrated_test: Metrics
    params: PlattParams
    reliability_raw: list[dict[str, object]] = field(default_factory=list)
    reliability_calibrated: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "variant": self.variant,
            "question": self.question,
            "test_raw": self.raw_test.as_dict(),
            "test_calibrated": self.calibrated_test.as_dict(),
            "platt": {
                "slope": self.params.slope,
                "intercept": self.params.intercept,
                "fitted_on": self.params.fitted_on,
                "log_loss_before": self.params.base_log_loss,
                "log_loss_after": self.params.fitted_log_loss,
            },
            "reliability_raw": self.reliability_raw,
            "reliability_calibrated": self.reliability_calibrated,
        }


@dataclass(slots=True)
class ExperimentReport:
    horizon_days: int
    requested: int
    labelled: int
    calibration_size: int
    test_size: int
    provider: str
    model: str
    variants: list[VariantResult] = field(default_factory=list)
    verdict: str = ""
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_days": self.horizon_days,
            "requested": self.requested,
            "labelled": self.labelled,
            "calibration_size": self.calibration_size,
            "test_size": self.test_size,
            "provider": self.provider,
            "model": self.model,
            "variants": [item.as_dict() for item in self.variants],
            "verdict": self.verdict,
            "limitations": self.limitations,
        }


async def run_experiment(
    session: AsyncSession,
    *,
    horizon_days: int = 7,
    sample: int = 300,
    client: JudgementClient | None = None,
) -> ExperimentReport:
    judge = client or get_judgement_client()
    if judge is None:
        raise JudgementError("未配置判官（JUDGEMENT_PROVIDER=none），无法实验")

    cases: list[EvalCase] = await select_cases(
        session, horizon_days=horizon_days, limit=sample, order="random"
    )
    if not cases:
        raise JudgementError(f"在 {horizon_days} 天 horizon 下没有可用样本")

    # 标签先算一次，两种措辞共用（保证对照的是措辞，不是标签）
    labelled: list[tuple[EvalCase, bool]] = []
    for case in cases:
        labelled.append((case, await _label(session, case, horizon_days)))

    report = ExperimentReport(
        horizon_days=horizon_days,
        requested=sample,
        labelled=len(labelled),
        calibration_size=0,
        test_size=0,
        provider=judge.provider,
        model="",
    )

    for variant, template in VARIANTS.items():
        question = NoulQuestion(instructions=template.format(horizon=horizon_days))
        observations: list[Observation] = []
        for case, outcome in labelled:
            try:
                response = await judge.ask(case.state[:MAX_STATE_CHARS], {"q": question})
            except JudgementError as exc:
                log.warning(
                    "experiment.call_failed", entity_id=case.entity_id, error=str(exc)[:120]
                )
                continue
            answer = response.answers.get("q")
            if answer is None or answer.noul is None:
                continue
            report.model = response.model or report.model
            observations.append(
                Observation(
                    key=f"entity:{case.entity_id}",
                    probability=round(float(answer.noul), 6),
                    outcome=outcome,
                    note=case.entity_name,
                )
            )

        if not observations:
            continue
        calibration_set, test_set = split_by_key(observations, ratio=0.5)
        if not calibration_set or not test_set:
            continue
        report.calibration_size = len(calibration_set)
        report.test_size = len(test_set)

        params = fit_platt(calibration_set)
        calibrated_test = calibrate(test_set, params)
        report.variants.append(
            VariantResult(
                variant=variant,
                question=template.format(horizon=horizon_days),
                raw_test=summarize(test_set),
                calibrated_test=summarize(calibrated_test),
                params=params,
                reliability_raw=[
                    {
                        "range": f"{bucket.lower:.2f}-{bucket.upper:.2f}",
                        "count": bucket.count,
                        "mean_probability": bucket.mean_probability,
                        "empirical_rate": bucket.empirical_rate,
                    }
                    for bucket in reliability_curve(test_set)
                ],
                reliability_calibrated=[
                    {
                        "range": f"{bucket.lower:.2f}-{bucket.upper:.2f}",
                        "count": bucket.count,
                        "mean_probability": bucket.mean_probability,
                        "empirical_rate": bucket.empirical_rate,
                    }
                    for bucket in reliability_curve(calibrated_test)
                ],
            )
        )

    report.limitations = [
        "标签仍是客观覆盖口径（T 之后是否出现新报道），只覆盖「事件是否还在发展」；",
        "escalation / downstream 等语义判断依旧没有客观标签，本实验无法验证它们；",
        "语料约 33 天，horizon 上限约 10 天；",
        "Platt 参数只在校准集上拟合，测试集数字才是结论；样本量仍偏小，置信区间较宽。",
    ]
    best = max(
        report.variants,
        key=lambda item: item.calibrated_test.skill,
        default=None,
    )
    if best is None:
        report.verdict = "实验没有产出可用结果"
    elif best.calibrated_test.skill > 0.05 and best.calibrated_test.ece < 0.15:
        report.verdict = (
            f"措辞 {best.variant} + Platt 校准后通过门禁"
            f"（skill={best.calibrated_test.skill}, ECE={best.calibrated_test.ece}）"
        )
    else:
        # 区分两种失败：有排序能力但没校准好（可救） vs 根本没有信息（不可救）。
        # 后者再怎么攒样本、调 Platt 都不会变好，必须说出来，否则会被误读成
        # 「skill 已经是 -0.005 了，再等等就过门」。
        raw_auc = best.raw_test.auc
        diagnostics = []
        if raw_auc < 0.55:
            details = (
                f"原始 AUC={raw_auc}（0.5=随机）说明判官对这些事件**没有区分能力**，"
                "不是校准不足。继续积累样本或重拟合 Platt 都不会改善排序；"
                "要提升只能换更强的判官（云端 Jev）或换一个真正可预测的问题口径。"
            )
        elif best.raw_test.skill < 0.05:
            details = (
                f"原始 AUC={raw_auc} 说明有一定排序能力，但 Brier skill "
                f"{best.raw_test.skill} 未超过基线；属于「有信号但概率不可用」。"
            )
        else:
            details = f"原始 AUC={raw_auc}，校准后仍未同时满足 skill>0.05 与 ECE<0.15。"
        diagnostics.append(details)
        report.verdict = (
            "未通过：所有措辞（含 Platt 校准后）都没能在锁定测试集上超过基线。"
            f"最好的一项是 {best.variant}，"
            f"skill={best.calibrated_test.skill}, ECE={best.calibrated_test.ece}。"
            + "".join(diagnostics)
            + "结论：当前判官在这些问题上不可用，推演保持标注「未经校准」"
        )
    return report
