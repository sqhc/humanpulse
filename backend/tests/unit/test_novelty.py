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
    assert result.score < n.THRESHOLD_RELATED
    assert result.confidence == "full"
    keys = [f.key for f in result.factors]
    assert keys == ["newness", "time_freshness", "source_diversity", "recency"]
    assert result.basis_zh == []


def test_no_neighbours_is_new_signal() -> None:
    """窗口内没有任何近邻 → 满分；缺失的近邻按最高新意处理，而不是 0。"""
    result = n.compute_novelty(
        max_similarity=None,
        nearest_hours=None,
        same_source=0,
        total_in_window=0,
        age_days=0.0,
        has_embedding=True,
    )
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


def test_factor_metric_slots_are_machine_readable() -> None:
    """前端「为什么新颖」槽位句要的数字必须由字段提供，不能靠 parse detail_zh。"""
    newness = n.newness_factor(0.753)
    assert newness.metric_unit == "percent"
    assert newness.metric_value == pytest.approx(75.3)

    freshness = n.time_freshness_factor(4.8)
    assert freshness.metric_unit == "hours"
    assert freshness.metric_value == pytest.approx(4.8)

    diversity = n.source_diversity_factor(same_source=3, total=20, other_sources=7)
    assert diversity.metric_unit == "outlets"
    assert diversity.metric_value == pytest.approx(7.0)  # 去重后的来源家数，不是 17 条稿子

    # 不给 other_sources 时不得瞎猜成条数差
    assert n.source_diversity_factor(same_source=3, total=20).metric_value is None

    recency = n.recency_factor(2.5)
    assert recency.metric_unit == "days"
    assert recency.metric_value == pytest.approx(2.5)


def test_absent_factors_have_no_metric_slot() -> None:
    """缺席因子不该给出槽位数字——否则前端会显示一个算不出来的值。"""
    assert n.source_diversity_factor(None, 0).metric_value is None
    assert n.recency_factor(None).metric_value is None
    assert n.source_diversity_factor(None, 0).value is None


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


def test_band_cuts_are_quantile_based() -> None:
    """分位数切点：样本足够时 p25/p75 应真正落在 25%/75% 位置，而不是手拍阈值。"""
    scores = [i / 100 for i in range(101)]  # 0.00 … 1.00
    cohort = n.cohort_from_scores(scores)
    assert cohort.fallback is False
    assert cohort.low == pytest.approx(0.25, abs=0.01)
    assert cohort.high == pytest.approx(0.75, abs=0.01)
    # 三档各占约 25 / 50 / 25
    bands = [cohort.band_of(s) for s in scores]
    high = bands.count(n.BAND_HIGH)
    covered = bands.count(n.BAND_COVERED)
    assert 20 <= high <= 30
    assert 20 <= covered <= 30


def test_small_cohort_falls_back_to_absolute_thresholds() -> None:
    """样本不足时分位数不可靠 → 退回手拍阈值，并显式标 fallback，不假装准。"""
    cohort = n.cohort_from_scores([0.1, 0.2, 0.3])
    assert cohort.fallback is True
    assert cohort.low == n.THRESHOLD_RELATED
    assert cohort.high == n.THRESHOLD_NEW


def test_percentile_rank_is_a_rank_not_a_point() -> None:
    """百分位是「比多少比例的条目更新」：最低分也有名次，最高分是 100。"""
    cohort = n.cohort_from_scores([i / 100 for i in range(101)])
    assert cohort.percentile_of(0.0) == pytest.approx(1.0)
    assert cohort.percentile_of(0.5) == pytest.approx(50.5, abs=1.0)
    assert cohort.percentile_of(1.0) == pytest.approx(100.0)
    # 并列值给同一名次
    assert cohort.percentile_of(0.5) == cohort.percentile_of(0.5)


def test_empty_cohort_does_not_crash() -> None:
    """空分布（库里没数据）也必须能返回，而不是除零。"""
    cohort = n.cohort_from_scores([])
    assert cohort.size == 0
    assert cohort.percentile_of(0.9) == 0.0
    assert cohort.band_of(0.9) == n.BAND_HIGH  # 退回绝对值阈值
    assert cohort.fallback is True


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


def test_recommendation_uses_relative_wording() -> None:
    """文案必须是相对口径，不能出现「真正的新」这类绝对主张。"""
    zh, en = n.recommendation(n.BAND_HIGH, 82.4)
    assert "相对新颖" in zh and "82" in zh
    assert "relatively new" in en.lower()
    assert "真正" not in zh and "truly" not in en.lower()
    covered_zh, _ = n.recommendation(n.BAND_COVERED, 12.0)
    assert "已覆盖" in covered_zh
    assert covered_zh != zh


def test_note_says_relative_not_calibrated() -> None:
    assert "相对" in n.NOTE_ZH and "未经" in n.NOTE_ZH
    lowered = n.NOTE_EN.lower()
    assert "relative" in lowered
    assert "calibrated=false" in lowered or "not a calibrated" in lowered


def test_helpers_are_timezone_safe() -> None:
    a = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    b = a + timedelta(hours=36)
    assert n.hours_between(a, b) == pytest.approx(36.0)
    assert n.age_days_between(a, b) == pytest.approx(1.5)
