"""DeepSeek 官方定价表（每 1M token 美元）。

来源：https://api-docs.deepseek.com/quick_start/pricing/ （2026-09 抓取）

| 模型 | 输入·缓存命中 | 输入·未命中 | 输出 |
| --- | --- | --- | --- |
| deepseek-flash | 0.003 | 0.15 | 0.60 |
| deepseek-v4-pro | 0.022 | 0.66 | 1.98 |

低谷价是高峰价的一半；高峰 = 周一至周五 01:00-04:00 与 06:00-10:00（UTC），
但节假日日历不在本程序内维护，因此遇到节假日会**略微高估**成本（宁可高估不要低估）。
单价可通过环境变量覆盖，方便厂商调价后不改代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"

# 高峰时段（UTC）：周一至周五的这些小时按高峰计价
PEAK_HOURS_UTC = ((1, 4), (6, 10))


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """每 1M token 的低谷单价（美元）。"""

    cache_hit: Decimal
    cache_miss: Decimal
    output: Decimal


# 低谷价（env 未配置时的默认值）
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "flash": ModelPrice(Decimal("0.003"), Decimal("0.15"), Decimal("0.60")),
    "pro": ModelPrice(Decimal("0.022"), Decimal("0.66"), Decimal("1.98")),
}

DEFAULT_PEAK_MULTIPLIER = Decimal("2")


def _decimal_env(name: str, fallback: Decimal) -> Decimal:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return fallback
    return value if value >= 0 else fallback


def price_tier(model: str) -> str:
    """把模型名映射到价位档（flash / pro）。"""
    name = (model or "").lower()
    if "pro" in name:
        return "pro"
    return "flash"


def price_for(model: str) -> ModelPrice:
    """取该模型的低谷单价；支持用 DEEPSEEK_PRICE_<TIER>_* 覆盖。"""
    tier = price_tier(model)
    base = DEFAULT_PRICES[tier]
    prefix = "DEEPSEEK_PRICE_" + tier.upper()
    return ModelPrice(
        cache_hit=_decimal_env(prefix + "_CACHE_HIT", base.cache_hit),
        cache_miss=_decimal_env(prefix + "_CACHE_MISS", base.cache_miss),
        output=_decimal_env(prefix + "_OUTPUT", base.output),
    )


def is_peak(moment: datetime) -> bool:
    """高峰时段判断（UTC；节假日未建模）。"""
    utc = moment.astimezone(UTC)
    if utc.weekday() >= 5:  # 周六/周日全天低谷
        return False
    return any(start <= utc.hour < end for start, end in PEAK_HOURS_UTC)


def peak_multiplier(moment: datetime) -> Decimal:
    if not is_peak(moment):
        return Decimal(1)
    return _decimal_env("DEEPSEEK_PEAK_MULTIPLIER", DEFAULT_PEAK_MULTIPLIER)


def cost_usd(
    model: str,
    *,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
    moment: datetime | None = None,
) -> Decimal:
    """按官方定价算成本；token 数除以 1M 后乘以单价。"""
    price = price_for(model)
    multiplier = peak_multiplier(moment or datetime.now(UTC))
    million = Decimal(1_000_000)
    raw = (
        Decimal(max(cache_hit_tokens, 0)) * price.cache_hit
        + Decimal(max(cache_miss_tokens, 0)) * price.cache_miss
        + Decimal(max(output_tokens, 0)) * price.output
    ) / million
    return (raw * multiplier).quantize(Decimal("0.000001"))


@dataclass(slots=True)
class TokenBundle:
    """一次（或多次重试累计的）token 用量。"""

    cache_hit: int = 0
    cache_miss: int = 0
    output: int = 0

    @property
    def tokens_in(self) -> int:
        return self.cache_hit + self.cache_miss

    def __add__(self, other: TokenBundle) -> TokenBundle:
        return TokenBundle(
            cache_hit=self.cache_hit + other.cache_hit,
            cache_miss=self.cache_miss + other.cache_miss,
            output=self.output + other.output,
        )
