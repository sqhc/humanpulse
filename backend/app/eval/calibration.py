"""概率校准：Platt scaling（2 参数）的拟合与应用。

为什么需要它：
实测发现 Laya 在客观子问题上的失败模式是**系统性偏低**——它说「约 8% 会发生」
的那批实际 94% 发生了，而高段（说 0.9 实际 0.96）还算准。纯温度缩放只能整体
变软/变锐，修不了这种整体偏移，所以用 Platt scaling：

    logit(p') = a * logit(p) + b

a 调节锐度，b 调节整体偏移。两个参数都在**校准集**上拟合，在**独立的锁定测试集**上报告。

方法学约束（这条比代码重要）：
校准参数只能在校准集上拟合，且测试集与校准集按实体切分、完全不重叠。
在同一批数据上拟合又评估，正是评估门存在的意义所要防的那种自欺。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.eval.metrics import Observation, log_loss


@dataclass(frozen=True, slots=True)
class PlattParams:
    slope: float
    intercept: float
    fitted_on: int
    base_log_loss: float
    fitted_log_loss: float


def _logit(probability: float) -> float:
    clamped = min(max(probability, 1e-6), 1 - 1e-6)
    return math.log(clamped / (1 - clamped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def apply_platt(probability: float, params: PlattParams) -> float:
    return _sigmoid(params.slope * _logit(probability) + params.intercept)


def _loss(observations: Sequence[Observation], slope: float, intercept: float) -> float:
    adjusted = [
        Observation(
            key=item.key,
            probability=_sigmoid(slope * _logit(item.probability) + intercept),
            outcome=item.outcome,
        )
        for item in observations
    ]
    return log_loss(adjusted)


def fit_platt(
    observations: Sequence[Observation],
    *,
    coarse_steps: int = 25,
    refine_rounds: int = 4,
) -> PlattParams:
    """粗到细的网格搜索拟合 (a, b)。

    刻意不引入 scipy：目标函数是二维、单峰性足够好，网格搜索 + 逐轮缩小区间
    既够用又零依赖，而且结果完全可复现（没有随机初始化）。
    """
    if not observations:
        return PlattParams(1.0, 0.0, 0, 0.0, 0.0)

    baseline = log_loss(observations)
    best_slope, best_intercept = 1.0, 0.0
    best_loss = baseline
    slope_lo, slope_hi = 0.05, 5.0
    intercept_lo, intercept_hi = -5.0, 5.0

    for round_index in range(refine_rounds):
        steps = coarse_steps if round_index == 0 else 15
        slope_step = (slope_hi - slope_lo) / (steps - 1)
        intercept_step = (intercept_hi - intercept_lo) / (steps - 1)
        for i in range(steps):
            slope = slope_lo + i * slope_step
            for j in range(steps):
                intercept = intercept_lo + j * intercept_step
                value = _loss(observations, slope, intercept)
                if value < best_loss:
                    best_loss = value
                    best_slope, best_intercept = slope, intercept
        # 围绕当前最优点收缩搜索区间
        span_slope = max(slope_step * 2, 0.01)
        span_intercept = max(intercept_step * 2, 0.01)
        slope_lo, slope_hi = best_slope - span_slope, best_slope + span_slope
        intercept_lo, intercept_hi = (
            best_intercept - span_intercept,
            best_intercept + span_intercept,
        )

    return PlattParams(
        slope=round(best_slope, 4),
        intercept=round(best_intercept, 4),
        fitted_on=len(observations),
        base_log_loss=round(baseline, 4),
        fitted_log_loss=round(best_loss, 4),
    )


def calibrate(observations: Sequence[Observation], params: PlattParams) -> list[Observation]:
    return [
        Observation(
            key=item.key,
            probability=round(apply_platt(item.probability, params), 6),
            outcome=item.outcome,
            note=item.note,
        )
        for item in observations
    ]


def split_by_key(
    observations: Sequence[Observation], *, ratio: float = 0.5
) -> tuple[list[Observation], list[Observation]]:
    """按 key 的稳定哈希切分，保证同一条预测不会同时出现在两边。

    不用 random：可复现比「看起来更随机」重要。
    """
    import hashlib

    calibration_set: list[Observation] = []
    test_set: list[Observation] = []
    threshold = int(ratio * 10_000)
    for item in observations:
        digest = hashlib.blake2b(item.key.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest, "big") % 10_000
        if bucket < threshold:
            calibration_set.append(item)
        else:
            test_set.append(item)
    return calibration_set, test_set
