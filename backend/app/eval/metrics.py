"""概率预测的评分函数（纯函数，不依赖数据库与模型）。

只实现本项目需要的那几个，并且每个都配一个**基线**——
没有基线的「准确率 0.8」是没意义的：在基率 0.2 的二分类上，
永远预测「不会发生」就能拿到 0.8 的准确率。

参考教程第六章的评测纪律：无重试、无回退、报基线、看概率质量而不只看 argmax。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observation:
    """一次可核对的历史预测：模型给的概率 vs 客观发生与否。"""

    key: str
    probability: float
    outcome: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    mean_probability: float
    empirical_rate: float


@dataclass(frozen=True, slots=True)
class CoveragePoint:
    coverage: float
    accuracy: float
    mean_decisiveness: float


def base_rate(observations: Sequence[Observation]) -> float:
    if not observations:
        return 0.0
    return sum(1 for item in observations if item.outcome) / len(observations)


def brier_score(observations: Sequence[Observation]) -> float:
    """平均平方误差；越低越好。"""
    if not observations:
        return 0.0
    return sum(
        (item.probability - (1.0 if item.outcome else 0.0)) ** 2 for item in observations
    ) / len(observations)


def brier_baseline(observations: Sequence[Observation]) -> float:
    """基线：对每个样本都预测样本基率（常数预测）。

    比「永远预测多数类」更强，所以用它当基线更严格。
    """
    if not observations:
        return 0.0
    rate = base_rate(observations)
    return sum((rate - (1.0 if item.outcome else 0.0)) ** 2 for item in observations) / len(
        observations
    )


def brier_skill_score(observations: Sequence[Observation]) -> float:
    """1 - 模型/基线。> 0 才算有信息量；<= 0 说明还不如直接报基率。"""
    baseline = brier_baseline(observations)
    if baseline <= 0:
        return 0.0
    return 1.0 - brier_score(observations) / baseline


def accuracy(observations: Sequence[Observation], *, threshold: float = 0.5) -> float:
    if not observations:
        return 0.0
    return sum(1 for item in observations if (item.probability >= threshold) == item.outcome) / len(
        observations
    )


def majority_accuracy(observations: Sequence[Observation]) -> float:
    """基线：永远猜多数类。"""
    if not observations:
        return 0.0
    rate = base_rate(observations)
    return max(rate, 1.0 - rate)


def log_loss(observations: Sequence[Observation]) -> float:
    """交叉熵；概率被夹到 [1e-6, 1-1e-6] 防止 log(0)。"""
    if not observations:
        return 0.0
    total = 0.0
    for item in observations:
        probability = min(max(item.probability, 1e-6), 1 - 1e-6)
        total += -math.log(probability if item.outcome else 1 - probability)
    return total / len(observations)


def expected_calibration_error(observations: Sequence[Observation], *, bins: int = 5) -> float:
    """按概率分箱，算 |平均预测 - 实际频率| 的加权平均。

    比准确率更能说明「0.7 到底是不是七成」。
    """
    if not observations or bins < 1:
        return 0.0
    width = 1.0 / bins
    error = 0.0
    for index in range(bins):
        lower = index * width
        upper = lower + width
        # 最后一箱包含右端点
        members = [
            item
            for item in observations
            if (lower <= item.probability < upper)
            or (index == bins - 1 and item.probability == upper)
        ]
        if not members:
            continue
        mean_probability = sum(item.probability for item in members) / len(members)
        empirical = sum(1 for item in members if item.outcome) / len(members)
        error += (len(members) / len(observations)) * abs(mean_probability - empirical)
    return error


def reliability_curve(
    observations: Sequence[Observation], *, bins: int = 5
) -> list[CalibrationBucket]:
    """可靠性曲线的数据点（前端/报告直接画）。"""
    if not observations or bins < 1:
        return []
    width = 1.0 / bins
    curve: list[CalibrationBucket] = []
    for index in range(bins):
        lower = index * width
        upper = lower + width
        members = [
            item
            for item in observations
            if (lower <= item.probability < upper)
            or (index == bins - 1 and item.probability == upper)
        ]
        if not members:
            continue
        curve.append(
            CalibrationBucket(
                lower=round(lower, 4),
                upper=round(upper, 4),
                count=len(members),
                mean_probability=round(sum(item.probability for item in members) / len(members), 4),
                empirical_rate=round(sum(1 for item in members if item.outcome) / len(members), 4),
            )
        )
    return curve


def risk_coverage(observations: Sequence[Observation], *, points: int = 10) -> list[CoveragePoint]:
    """按「果断程度」|p-0.5| 从高到低排序，看保留前 k% 时的准确率。

    如果模型真的知道自己什么时候不确定，这条曲线应当单调下降：
    越果断的部分越准。不下降说明概率没有被用来表达不确定性。
    """
    if not observations:
        return []
    ordered = sorted(observations, key=lambda item: abs(item.probability - 0.5), reverse=True)
    curve: list[CoveragePoint] = []
    total = len(ordered)
    step = max(1, total // points)
    for count in range(step, total + 1, step):
        subset = ordered[:count]
        correct = sum(1 for item in subset if (item.probability >= 0.5) == item.outcome)
        decisiveness = sum(abs(item.probability - 0.5) for item in subset) / count
        curve.append(
            CoveragePoint(
                coverage=round(count / total, 4),
                accuracy=round(correct / count, 4),
                mean_decisiveness=round(decisiveness, 4),
            )
        )
    return curve
