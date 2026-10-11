"""Platt 校准与切分：拟合不能作弊，切分不能重叠。"""

from __future__ import annotations

import pytest

from app.eval.calibration import (
    PlattParams,
    apply_platt,
    calibrate,
    fit_platt,
    split_by_key,
)
from app.eval.metrics import Observation, log_loss


def _inverted(count: int = 60) -> list[Observation]:
    """模型系统性偏低：说 0.1 的其实总会发生。"""
    observations = []
    for index in range(count):
        observations.append(
            Observation(
                key=f"k{index}",
                probability=0.1 + (index % 3) * 0.02,
                outcome=True,
            )
        )
    return observations


def test_identity_params_are_identity() -> None:
    params = PlattParams(
        slope=1.0, intercept=0.0, fitted_on=0, base_log_loss=0.0, fitted_log_loss=0.0
    )
    for probability in (0.01, 0.2, 0.5, 0.8, 0.99):
        assert apply_platt(probability, params) == pytest.approx(probability, abs=1e-6)


def test_fit_reduces_log_loss_on_inverted_data() -> None:
    observations = _inverted()
    params = fit_platt(observations)
    before = log_loss(observations)
    after = log_loss(calibrate(observations, params))
    assert after < before
    assert params.fitted_log_loss < params.base_log_loss


def test_fit_recovers_base_rate_for_uninformative_model() -> None:
    """模型完全没信息量时，最优解近似「常数预测基率」——表现为斜率趋近 0。"""
    observations = _inverted()
    params = fit_platt(observations)
    assert params.slope < 0.5  # 几乎忽略模型输入


def test_calibrated_probabilities_stay_in_range() -> None:
    params = fit_platt(_inverted())
    for item in calibrate(_inverted(), params):
        assert 0.0 <= item.probability <= 1.0


def test_fit_keeps_identity_when_model_is_already_good() -> None:
    # 已经校准且果断的模型，拟合不该把它改坏
    observations = [
        Observation(key="a", probability=0.95, outcome=True),
        Observation(key="b", probability=0.9, outcome=True),
        Observation(key="c", probability=0.1, outcome=False),
        Observation(key="d", probability=0.05, outcome=False),
    ] * 10
    params = fit_platt(observations)
    calibrated = calibrate(observations, params)
    assert log_loss(calibrated) <= log_loss(observations) + 1e-6


def test_fit_handles_empty_input() -> None:
    params = fit_platt([])
    assert params.slope == 1.0 and params.intercept == 0.0


def test_split_is_deterministic_and_disjoint() -> None:
    observations = [
        Observation(key=f"entity:{i}", probability=0.5, outcome=i % 2 == 0) for i in range(200)
    ]
    first_calibration, first_test = split_by_key(observations)
    second_calibration, second_test = split_by_key(observations)

    assert [item.key for item in first_calibration] == [item.key for item in second_calibration]
    assert [item.key for item in first_test] == [item.key for item in second_test]

    calibration_keys = {item.key for item in first_calibration}
    test_keys = {item.key for item in first_test}
    assert not (calibration_keys & test_keys)
    assert len(calibration_keys) + len(test_keys) == len(observations)


def test_split_respects_ratio() -> None:
    observations = [Observation(key=f"k{i}", probability=0.5, outcome=True) for i in range(1000)]
    calibration, test = split_by_key(observations, ratio=0.3)
    assert 0.25 < len(calibration) / 1000 < 0.35
    assert len(calibration) + len(test) == 1000
