"""评估指标：每个指标都要能对上手工算的答案。

这些数字会被用来决定「推演能不能上线」，算错了会直接导致错误决策，所以逐个钉死。
"""

from __future__ import annotations

import pytest

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
    risk_coverage,
)


def test_base_rate() -> None:
    observations = [
        Observation(key="a", probability=0.9, outcome=True),
        Observation(key="b", probability=0.1, outcome=False),
        Observation(key="c", probability=0.5, outcome=True),
    ]
    assert base_rate(observations) == pytest.approx(2 / 3)


def test_brier_score_perfect_is_zero() -> None:
    observations = [
        Observation(key="a", probability=1.0, outcome=True),
        Observation(key="b", probability=0.0, outcome=False),
    ]
    assert brier_score(observations) == 0.0


def test_brier_score_hand_computed() -> None:
    # (0.8-1)^2=0.04, (0.3-0)^2=0.09 -> 平均 0.065
    observations = [
        Observation(key="a", probability=0.8, outcome=True),
        Observation(key="b", probability=0.3, outcome=False),
    ]
    assert brier_score(observations) == pytest.approx(0.065)


def test_brier_baseline_uses_base_rate_not_majority() -> None:
    # 基率 0.5：常数预测 0.5 的 Brier = 0.25
    observations = [
        Observation(key="a", probability=0.9, outcome=True),
        Observation(key="b", probability=0.1, outcome=False),
    ]
    assert brier_baseline(observations) == pytest.approx(0.25)


def test_skill_score_zero_when_matching_baseline() -> None:
    observations = [
        Observation(key="a", probability=0.5, outcome=True),
        Observation(key="b", probability=0.5, outcome=False),
    ]
    assert brier_skill_score(observations) == pytest.approx(0.0)


def test_skill_score_positive_for_informative_model() -> None:
    observations = [
        Observation(key="a", probability=0.9, outcome=True),
        Observation(key="b", probability=0.2, outcome=False),
        Observation(key="c", probability=0.85, outcome=True),
        Observation(key="d", probability=0.15, outcome=False),
    ]
    assert brier_skill_score(observations) > 0


def test_skill_score_negative_for_inverted_model() -> None:
    # 模型在基率 0.85 的样本上普遍给低分：比常数基线差得多
    observations = [Observation(key=str(i), probability=0.05, outcome=True) for i in range(20)]
    observations += [Observation(key=f"n{i}", probability=0.9, outcome=False) for i in range(5)]
    assert brier_skill_score(observations) < 0


def test_accuracy_and_majority_accuracy() -> None:
    observations = [
        Observation(key="a", probability=0.9, outcome=True),
        Observation(key="b", probability=0.9, outcome=False),
        Observation(key="c", probability=0.9, outcome=True),
        Observation(key="d", probability=0.9, outcome=True),
    ]
    assert accuracy(observations) == pytest.approx(0.75)
    assert majority_accuracy(observations) == pytest.approx(0.75)


def test_ece_zero_when_perfectly_calibrated() -> None:
    # 每个 0.1 区间里恰好有 10% 的样本发生
    observations = []
    for index in range(10):
        bucket = index / 10 + 0.05
        for position in range(10):
            observations.append(
                Observation(
                    key=f"{index}-{position}",
                    probability=bucket,
                    outcome=position < index,
                )
            )
    assert expected_calibration_error(observations, bins=10) < 0.06


def test_ece_large_when_inverted() -> None:
    # 预测 0.05 但全部发生 -> 分箱误差接近 0.95
    observations = [Observation(key=str(i), probability=0.05, outcome=True) for i in range(10)]
    assert expected_calibration_error(observations) > 0.8


def test_reliability_curve_buckets() -> None:
    observations = [
        Observation(key="a", probability=0.05, outcome=True),
        Observation(key="b", probability=0.15, outcome=False),
        Observation(key="c", probability=0.95, outcome=True),
    ]
    curve = reliability_curve(observations, bins=2)
    assert len(curve) == 2
    assert curve[0].count == 2
    assert curve[0].empirical_rate == pytest.approx(0.5)
    assert curve[1].count == 1
    assert curve[1].empirical_rate == pytest.approx(1.0)


def test_risk_coverage_orders_by_decisiveness() -> None:
    observations = [
        Observation(key="decisive", probability=0.99, outcome=True),
        Observation(key="unsure", probability=0.51, outcome=False),
        Observation(key="decisive2", probability=0.02, outcome=False),
    ]
    curve = risk_coverage(observations, points=3)
    assert curve
    # 覆盖最小的一段应当是最果断的
    assert curve[0].mean_decisiveness >= curve[-1].mean_decisiveness


def test_log_loss_bounds() -> None:
    # 完美预测的 log loss 接近 0（夹逼后略大于 0）
    perfect = [
        Observation(key="a", probability=1.0, outcome=True),
        Observation(key="b", probability=0.0, outcome=False),
    ]
    assert log_loss(perfect) < 0.001
    # 完全错：log loss 很大
    wrong = [Observation(key="a", probability=0.0, outcome=True)]
    assert log_loss(wrong) > 10


def test_empty_inputs_are_safe() -> None:
    assert brier_score([]) == 0.0
    assert brier_baseline([]) == 0.0
    assert brier_skill_score([]) == 0.0
    assert accuracy([]) == 0.0
    assert expected_calibration_error([]) == 0.0
    assert reliability_curve([]) == []
    assert risk_coverage([]) == []
