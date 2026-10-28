"""判官概率校准：将模型输出的原始概率映射为真实频率。

为什么需要它：
判官模型（如 Laya）经常存在过自信（Overconfident）
或欠自信问题，导致 ECE（Expected Calibration Error）较高。
通过 Isotonic Regression 或 Platt Scaling，我们可以让 0.7 的预测概率
真正对应 70% 的兑现率。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class CalibrationPair:
    """一个预测样本：(预测概率, 实际结果)。"""

    predicted: float
    actual: bool


class Calibrator(Protocol):
    """校准器契约。"""

    def calibrate(self, prob: float) -> float: ...


class IdentityCalibrator:
    """默认校准器：不对概率做任何修改。"""

    def calibrate(self, prob: float) -> float:
        return prob


class IsotonicCalibrator:
    """保序回归校准器（简单实现）。

    如果安装了 scikit-learn，建议使用 sklearn.isotonic.IsotonicRegression。
    这里提供一个基础的经验分布映射实现。
    """

    def __init__(self, pairs: list[CalibrationPair]):
        # 按预测概率排序
        sorted_pairs = sorted(pairs, key=lambda p: p.predicted)
        self.points = [p.predicted for p in sorted_pairs]

        # 计算累积兑现率作为校准值
        outcomes = [1.0 if p.actual else 0.0 for p in sorted_pairs]
        self.calibrated = []

        # 简单的滑动窗口平均或累积平均
        current_sum = 0.0
        for i, val in enumerate(outcomes):
            current_sum += val
            self.calibrated.append(current_sum / (i + 1))

    def calibrate(self, prob: float) -> float:
        if not self.points:
            return prob
        # 线性插值
        import bisect

        idx = bisect.bisect_left(self.points, prob)
        if idx == 0:
            return self.calibrated[0]
        if idx == len(self.points):
            return self.calibrated[-1]

        # 简单的线性插值
        p0, p1 = self.points[idx - 1], self.points[idx]
        c0, c1 = self.calibrated[idx - 1], self.calibrated[idx]
        return c0 + (c1 - c0) * (prob - p0) / (p1 - p0)


def get_calibrator(pairs: list[CalibrationPair | None]) -> Calibrator:
    """根据历史样本生成最合适的校准器。"""
    valid_pairs = [p for p in pairs if p is not None]
    if len(valid_pairs) < 10:  # 样本太少，不进行校准
        return IdentityCalibrator()
    return IsotonicCalibrator(valid_pairs)
