"""定价表：数字必须与官方页面一致，且缓存命中/未命中要分开计。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.llm.pricing import TokenBundle, cost_usd, is_peak, peak_multiplier, price_for, price_tier

OFF_PEAK = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)  # 周日 -> 全天低谷
PEAK = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)  # 周一 02:00 -> 高峰


def test_official_defaults() -> None:
    flash = price_for("deepseek-flash")
    assert flash.cache_hit == Decimal("0.003")
    assert flash.cache_miss == Decimal("0.15")
    assert flash.output == Decimal("0.60")
    pro = price_for("deepseek-v4-pro")
    assert pro.cache_hit == Decimal("0.022")
    assert pro.cache_miss == Decimal("0.66")
    assert pro.output == Decimal("1.98")


def test_price_tier_by_model_name() -> None:
    assert price_tier("deepseek-v4-pro") == "pro"
    assert price_tier("deepseek-flash") == "flash"
    assert price_tier("something-unknown") == "flash"


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_PRICE_FLASH_OUTPUT", "9.99")
    assert price_for("deepseek-flash").output == Decimal("9.99")


def test_peak_window() -> None:
    assert is_peak(OFF_PEAK) is False
    assert is_peak(PEAK) is True
    assert is_peak(datetime(2026, 9, 28, 0, 30, tzinfo=UTC)) is False
    assert is_peak(datetime(2026, 9, 28, 4, 0, tzinfo=UTC)) is False
    assert is_peak(datetime(2026, 9, 28, 8, 0, tzinfo=UTC)) is True
    assert peak_multiplier(OFF_PEAK) == Decimal(1)
    assert peak_multiplier(PEAK) == Decimal(2)


def test_cost_math_matches_official_table() -> None:
    # 0.1M 命中 * 0.003 + 0.01M 未命中 * 0.15 + 0.005M 输出 * 0.6 = 0.0003 + 0.0015 + 0.003
    cost = cost_usd(
        "deepseek-flash",
        cache_hit_tokens=100_000,
        cache_miss_tokens=10_000,
        output_tokens=5_000,
        moment=OFF_PEAK,
    )
    assert cost == Decimal("0.004800")


def test_peak_costs_double() -> None:
    kwargs = {"cache_hit_tokens": 0, "cache_miss_tokens": 10_000, "output_tokens": 5_000}
    assert cost_usd("deepseek-flash", moment=PEAK, **kwargs) == (
        cost_usd("deepseek-flash", moment=OFF_PEAK, **kwargs) * 2
    )


def test_cache_hit_is_far_cheaper() -> None:
    hit = cost_usd(
        "deepseek-flash",
        cache_hit_tokens=1_000_000,
        cache_miss_tokens=0,
        output_tokens=0,
        moment=OFF_PEAK,
    )
    miss = cost_usd(
        "deepseek-flash",
        cache_hit_tokens=0,
        cache_miss_tokens=1_000_000,
        output_tokens=0,
        moment=OFF_PEAK,
    )
    assert hit == Decimal("0.003000")
    assert miss == Decimal("0.150000")


def test_negative_tokens_are_clamped() -> None:
    assert (
        cost_usd(
            "deepseek-flash",
            cache_hit_tokens=-5,
            cache_miss_tokens=-5,
            output_tokens=-5,
            moment=OFF_PEAK,
        )
        == 0
    )


def test_token_bundle_addition() -> None:
    a = TokenBundle(cache_hit=10, cache_miss=5, output=3)
    b = TokenBundle(cache_hit=1, cache_miss=2, output=4)
    total = a + b
    assert total.cache_hit == 11
    assert total.cache_miss == 7
    assert total.output == 7
    assert total.tokens_in == 18
