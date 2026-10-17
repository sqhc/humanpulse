"""Signal novelty 纯函数：权重归一化、缺席因子、阈值分档。

这里只测确定性核心（app/pipeline/novelty.py），DB 路径由冒烟脚本覆盖——
和 test_predictions.py 同一口径：轻量、无数据库。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.pipeline import novelty as n


def test_perfect_duplicate_is_covered() -> None:
    """窗口内有一篇几乎一模一样的报道 → covered，且因子可溯源。"""
    result = n.compute_novelty(
        max_similarity=0.98,
        nearest_hours=1.0,
        same_source=4,
        total_in_window=5,
        age_days=0.0,
        has_embedding=True,
    )
    assert result.status == n.STATUS_COVERED
    assert result.score < n.THRESHOLD_RELATED
    assert result.confidence == "full"
    keys = [f.key for f in result.factors]
    assert keys == ["newness", "time_freshness", "source_diversity", "recency"]
    assert result.basis_zh == []


def test_no_neighbours_is_new_signal() -> None:
    """窗口内没有任何近邻 → new；缺失的近邻按最高新意处理，而不是 0。"""
    result = n.compute_novelty(
        max_similarity=None,
        nearest_hours=None,
        same_source=0,
        total_in_window=0,
        age_days=0.0,
        has_embedding=True,
    )
    assert result.status == n.STATUS_NEW
    assert result.score == pytest.approx(1.0)


def test_recency_decays_with_age() -> None:
    """方向必须是「越新越高」，不是草案里反过来写的 min(1, 天数/30)。"""
    fresh = n.recency_factor(0.0)
    old = n.recency_factor(30.0)
    stale = n.recency_factor(90.0)
    assert fresh.value == 1.0
    assert old.value == 0.0
    assert stale.value == 0.0


def test_time_freshness_decays_with_gap() -> None:
    assert n.time_freshness_factor(None).value == 1.0
    assert n.time_freshness_factor(0.0).value == 0.0
    # τ=48h 处应为 1-e^-1 ≈ 0.632
    assert n.time_freshness_factor(48.0).value == pytest.approx(0.6321, abs=1e-4)


def test_missing_embedding_drops_vector_factors_and_renormalises() -> None:
    """没有向量：向量因子缺席（value=None）、不参与、权重重新归一化，并标 partial。"""
    result = n.compute_novelty(
        max_similarity=None,
        nearest_hours=None,
        same_source=0,
        total_in_window=10,
        age_days=0.0,
        has_embedding=False,
    )
    assert result.confidence == "partial"
    keys = [f.key for f in result.factors]
    assert "newness" not in keys
    assert "time_freshness" not in keys
    assert result.basis_zh and result.basis_en
    # 只剩 source_diversity(1.0) 与 recency(1.0)，重新归一化后仍是 1.0
    assert result.score == pytest.approx(1.0)


def test_absent_factor_weight_is_renormalised_not_zeroed() -> None:
    """来源分布无法计算（窗口为空）时，不能静默按 0 拉低分数。

    归一化的正确含义是「这一项既不帮也不害）：分数 = 其余项按权重的加权平均。
    若错误地把它当 0 分并保留原权重，分子会被拉低 —— 正是要避免的。
    """
    dropped = n.compute_novelty(
        max_similarity=0.0,
        nearest_hours=48.0,
        same_source=None,
        total_in_window=0,
        age_days=0.0,
        has_embedding=True,
    )
    assert any(f.key == "source_diversity" and f.value is None for f in dropped.factors)

    active = [f for f in dropped.factors if f.value is not None]
    renormalised = sum(f.value * f.weight for f in active) / sum(f.weight for f in active)
    zeroed = sum(f.value * f.weight for f in active)  # 缺席项保留权重并填 0
    assert dropped.score == pytest.approx(round(renormalised, 4))
    assert dropped.score > zeroed


def test_status_thresholds() -> None:
    assert n.status_of(0.65) == n.STATUS_NEW
    assert n.status_of(0.6499) == n.STATUS_RELATED
    assert n.status_of(0.35) == n.STATUS_RELATED
    assert n.status_of(0.3499) == n.STATUS_COVERED


def test_score_stays_in_unit_interval() -> None:
    """极端输入不得越界（相似度给 >1、时间为负等脏数据）。"""
    result = n.compute_novelty(
        max_similarity=1.5,
        nearest_hours=-5.0,
        same_source=-3,
        total_in_window=4,
        age_days=-2.0,
        has_embedding=True,
    )
    assert 0.0 <= result.score <= 1.0
    for factor in result.factors:
        if factor.value is not None:
            assert 0.0 <= factor.value <= 1.0


def test_recommendation_follows_status() -> None:
    zh, en = n.recommendation(n.STATUS_NEW, 7)
    assert "7" in zh and "7" in en
    covered_zh, _ = n.recommendation(n.STATUS_COVERED, 7)
    assert covered_zh != zh


def test_helpers_are_timezone_safe() -> None:
    a = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    b = a + timedelta(hours=36)
    assert n.hours_between(a, b) == pytest.approx(36.0)
    assert n.age_days_between(a, b) == pytest.approx(1.5)
