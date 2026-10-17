"""Signal：文档级 novelty（这篇是不是相对新的信息）。

设计原则（写进代码，便于审计）：
- 只吃确定性信号：向量近邻相似度、时间间隔、来源分布、时间新近度。**不碰任何概率模型输出**，
  因此与「判官概率未过评估门」的约束无关，也不构成一条新的未校准能力。
- 每个因子取值都在 [0,1]；数据缺失时该因子**不参与**加权（权重重新归一化），
  而不是静默填 0 或 1 —— 缺失会通过 `basis_zh` / `confidence=partial` 显式暴露。
- 档位按**分位数**（p75 / p25）切，不手拍绝对值：手拍的 0.65/0.35 在真实分布上会让
  85% 的条目挤进中间档，三色退化成一片黄。分位数天然保证三档各占 ~25/50/25。
- 所以档位是**相对口径**：「相对新颖」= 比 75% 的近期报道更新，而不是「这是真正的新信息」。
  我们没有任何人工标注证明后者，`calibrated=False` 固定保留。

因子定义（默认权重 w1..w4 = 0.4/0.2/0.2/0.2，Σw = 1）：

1. newness  = 1 - 时间窗内最大余弦相似度（无近邻记 1.0；无向量则缺席）
2. time_freshness = 1 - exp(-Δt/τ)，Δt = 与**最相似**近邻的发布时间间隔，τ = 48h
   （紧跟一篇几乎相同的报道 → 0；没有近邻 → 1）
3. source_diversity = 1 - 窗内同源占比（同一家源霸屏 → 低；多源覆盖 → 高）
4. recency = 1 - min(1, 距今天数/30)（今天 → 1；30 天前及更早 → 0）

注意：早期群里草案把 recency 写成 `min(1, 天数/30)`，方向是反的（越老越高）；这里已修正。
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

# ---- 可调参（默认值；调用方可通过接口 query 覆盖 horizon / tau） ----

W_NEWNESS = 0.4
W_TIME_FRESHNESS = 0.2
W_SOURCE_DIVERSITY = 0.2
W_RECENCY = 0.2

TAU_HOURS = 48.0
HORIZON_DAYS = 7
RECENCY_SPAN_DAYS = 30.0

PERCENTILE_NEW = 75.0
PERCENTILE_COVERED = 25.0

# 分位切点算不准时的兜底阈值（cohort 样本 < MIN_COHORT）
THRESHOLD_NEW = 0.65
THRESHOLD_RELATED = 0.35
MIN_COHORT = 30

COHORT_TTL_SECONDS = 15 * 60

# 档位：high = 相对新颖（前 25%），mid = 中间档，covered = 近期已覆盖（末 25%）。
BAND_HIGH = "high"
BAND_MID = "mid"
BAND_COVERED = "covered"

NOTE_ZH = (
    "档位按分位数（p75/p25）相对切分：相对新颖 = 比 75% 的近期报道更新，"
    "近期已覆盖 = 排在末 25%。这是相对切分，不是绝对校准——未经人工标注对齐，"
    "calibrated=false，仅供排序与提示参考。"
)
NOTE_EN = (
    "Tiers are relative quantile cuts (p75/p25): 'relatively new' means newer than 75% of recent "
    "coverage, 'recently covered' means bottom 25%. This is a relative split, not a calibrated "
    "claim: not aligned with human labels, calibrated=false, for ranking and hinting only."
)

MISSING_EMBEDDING_ZH = "库内没有该文档的向量，向量相关因子不参与计算，权重已重新归一化。"
MISSING_EMBEDDING_EN = (
    "No stored embedding for this document; vector-based factors were dropped and weights "
    "renormalised."
)


@dataclass(frozen=True)
class NoveltyFactor:
    key: str
    label_zh: str
    label_en: str
    value: float | None
    weight: float
    detail_zh: str
    detail_en: str
    # 机器可读的槽位数字：前端拼「为什么新颖」时直接取用，
    # 不必去 parse detail_zh 的自然语言（改一个字就会把前端拼串弄坏）。
    metric_value: float | None = None
    metric_unit: str = ""
    metric_label_zh: str = ""
    metric_label_en: str = ""

    @property
    def contribution(self) -> float:
        return 0.0 if self.value is None else self.value * self.weight


@dataclass(frozen=True)
class NoveltyScore:
    score: float
    factors: list[NoveltyFactor]
    basis_zh: list[str]
    basis_en: list[str]
    confidence: str


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def newness_factor(max_similarity: float | None) -> NoveltyFactor:
    """1 - 窗内最大相似度。max_similarity=None 表示没有可比较的近邻。"""
    if max_similarity is None:
        return NoveltyFactor(
            key="newness",
            label_zh="新意",
            label_en="newness",
            value=1.0,
            weight=W_NEWNESS,
            detail_zh="时间窗内没有可比对的其它报道，按最高新意处理。",
            detail_en="No comparable coverage inside the window; treated as maximally new.",
        )
    value = _clamp(1.0 - _clamp(max_similarity))
    return NoveltyFactor(
        key="newness",
        label_zh="新意",
        label_en="newness",
        value=value,
        weight=W_NEWNESS,
        detail_zh=f"窗口内最相似报道的余弦相似度 {max_similarity:.3f}，新意 = 1 - 相似度。",
        detail_en=f"Top-1 neighbour similarity {max_similarity:.3f}; newness = 1 - similarity.",
        metric_value=round(_clamp(max_similarity) * 100.0, 1),
        metric_unit="percent",
        metric_label_zh="与最相似报道的相似度",
        metric_label_en="similarity to the most similar report",
    )


def time_freshness_factor(
    nearest_hours: float | None, tau_hours: float = TAU_HOURS
) -> NoveltyFactor:
    """1 - exp(-Δt/τ)。nearest_hours=None 表示窗口内没有近邻。"""
    if nearest_hours is None:
        return NoveltyFactor(
            key="time_freshness",
            label_zh="时间新鲜度",
            label_en="time freshness",
            value=1.0,
            weight=W_TIME_FRESHNESS,
            detail_zh="窗口内没有近邻报道，视为无重复压力。",
            detail_en="No nearby coverage in the window; no repetition pressure.",
        )
    hours = max(0.0, float(nearest_hours))
    value = _clamp(1.0 - math.exp(-hours / tau_hours))
    return NoveltyFactor(
        key="time_freshness",
        label_zh="时间新鲜度",
        label_en="time freshness",
        value=value,
        weight=W_TIME_FRESHNESS,
        detail_zh=f"与最相似近邻相隔 {hours:.1f} 小时，τ={tau_hours:.0f}h。",
        detail_en=f"Nearest similar report was {hours:.1f}h away; tau={tau_hours:.0f}h.",
        metric_value=round(hours, 1),
        metric_unit="hours",
        metric_label_zh="距最相似近邻的时间间隔",
        metric_label_en="time since the most similar report",
    )


def source_diversity_factor(
    same_source: int | None, total: int | None, other_sources: int | None = None
) -> NoveltyFactor:
    """1 - 窗内同源占比。total=0 时该因子缺席（不猜）。

    other_sources 是**不同来源的个数**（不是条数）：文案里的「{M} 家不同来源」
    必须用去重后的来源数，否则会把 124 篇稿子说成 124 家媒体。
    """
    if not total or total <= 0 or same_source is None:
        return NoveltyFactor(
            key="source_diversity",
            label_zh="来源多样性",
            label_en="source diversity",
            value=None,
            weight=W_SOURCE_DIVERSITY,
            detail_zh="窗口内没有其它已入库报道，来源分布无法计算，本因子不参与。",
            detail_en=(
                "No other stored coverage in the window; source mix undefined, factor dropped."
            ),
        )
    share = _clamp(same_source / total)
    value = _clamp(1.0 - share)
    return NoveltyFactor(
        key="source_diversity",
        label_zh="来源多样性",
        label_en="source diversity",
        value=value,
        weight=W_SOURCE_DIVERSITY,
        detail_zh=f"窗口内 {total} 篇中有 {same_source} 篇来自同一来源（占比 {share:.0%}）。",
        detail_en=f"{same_source} of {total} window items share this source ({share:.0%}).",
        metric_value=None if other_sources is None else float(other_sources),
        metric_unit="outlets",
        metric_label_zh="窗口内其它来源家数（去重）",
        metric_label_en="other distinct outlets in the window",
    )


def recency_factor(age_days: float | None, span_days: float = RECENCY_SPAN_DAYS) -> NoveltyFactor:
    """1 - min(1, 距今天数 / 30)。"""
    if age_days is None:
        return NoveltyFactor(
            key="recency",
            label_zh="时效",
            label_en="recency",
            value=None,
            weight=W_RECENCY,
            detail_zh="缺少发布时间，时效无法计算，本因子不参与。",
            detail_en="No publication time available; recency undefined, factor dropped.",
        )
    days = max(0.0, float(age_days))
    value = _clamp(1.0 - _clamp(days / span_days))
    return NoveltyFactor(
        key="recency",
        label_zh="时效",
        label_en="recency",
        value=value,
        weight=W_RECENCY,
        detail_zh=f"距参考时刻 {days:.1f} 天，{span_days:.0f} 天线性衰减到 0。",
        detail_en=f"{days:.1f} days old; linear decay to 0 over {span_days:.0f} days.",
        metric_value=round(days, 1),
        metric_unit="days",
        metric_label_zh="距发布天数",
        metric_label_en="days since publication",
    )


def compute_novelty(
    *,
    max_similarity: float | None,
    nearest_hours: float | None,
    same_source: int | None,
    total_in_window: int | None,
    age_days: float | None,
    has_embedding: bool,
    tau_hours: float = TAU_HOURS,
    other_sources: int | None = None,
) -> NoveltyScore:
    """四因子加权，返回**纯分数**。档位/百分位由 cohort 另行判定（见 classify）。

    other_sources 只影响返回的槽位数字（「{M} 家不同来源」），不参与加权。
    """
    factors: list[NoveltyFactor] = []
    basis_zh: list[str] = []
    basis_en: list[str] = []

    if has_embedding:
        factors.append(newness_factor(max_similarity))
        factors.append(time_freshness_factor(nearest_hours, tau_hours))
    else:
        basis_zh.append(MISSING_EMBEDDING_ZH)
        basis_en.append(MISSING_EMBEDDING_EN)
    factors.append(
        source_diversity_factor(same_source, total_in_window, other_sources=other_sources)
    )
    factors.append(recency_factor(age_days))

    # 向量缺失时“时间新鲜度”同样无从谈起（它依赖最相似近邻），一并标为缺席，
    # 避免只剩两三个因子时权重口径含混。
    if not has_embedding:
        factors = [f for f in factors if f.key != "time_freshness"]

    active = [f for f in factors if f.value is not None]
    weight_sum = sum(f.weight for f in active)
    score = 0.0 if weight_sum <= 0 else sum(f.contribution for f in active) / weight_sum
    score = round(_clamp(score), 4)

    if metadata_only := not has_embedding:
        basis_zh.append("confidence=partial：本分数只由时间与来源因子构成，不等价于完整 novelty。")
        basis_en.append("confidence=partial: score uses time/source factors only.")

    return NoveltyScore(
        score=score,
        factors=factors,
        basis_zh=basis_zh,
        basis_en=basis_en,
        confidence="partial" if metadata_only else "full",
    )


def _as_score(value: float) -> float:
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return 0.0


class Cohort:
    """全局分布快照：p25/p75 切点 + 排名用的已排序分数表。

    这是「全局统计」而非单文档属性，所以缓存而不是每请求重算（全量重建实测 ~0.3–0.9s，
    超 0.5s 预算）。窗口或 τ 变了就是另一个分布，缓存键随之改变。
    """

    def __init__(
        self, raw: Sequence[float], cuts: tuple[float, float], window_days: int, tau_hours: float
    ) -> None:
        self.scores = sorted(_as_score(x) for x in raw)
        self.low, self.high = cuts
        self.window_days = window_days
        self.tau_hours = tau_hours
        self.fallback = len(self.scores) < MIN_COHORT

    @property
    def size(self) -> int:
        return len(self.scores)

    def percentile_of(self, score: float) -> float:
        """比 cohort 里多少比例的条目更新（0-100，含并列）。"""
        if not self.scores:
            return 0.0
        rank = bisect.bisect_right(self.scores, _as_score(score))
        return round(rank / len(self.scores) * 100.0, 1)

    def band_of(self, score: float) -> str:
        score = _as_score(score)
        if score >= self.high:
            return BAND_HIGH
        if score >= self.low:
            return BAND_MID
        return BAND_COVERED


def cohort_from_scores(
    raw: Sequence[float], *, window_days: int = HORIZON_DAYS, tau_hours: float = TAU_HOURS
) -> Cohort:
    """从已算出的分数列表建分布。样本不足时退回手拍阈值，并标 fallback=True。"""
    ordered = sorted(_as_score(x) for x in raw)
    if len(ordered) < MIN_COHORT:
        return Cohort(
            raw,
            (THRESHOLD_RELATED, THRESHOLD_NEW),
            window_days=window_days,
            tau_hours=tau_hours,
        )
    cuts = (_quantile(ordered, 25.0), _quantile(ordered, 75.0))
    return Cohort(raw, cuts, window_days=window_days, tau_hours=tau_hours)


def _quantile(ordered: Sequence[float], pct: float) -> float:
    """线性插值分位点（ordered 已升序）。"""
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * _clamp(pct / 100.0)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[int(position)])
    share = position - low
    return float(ordered[low]) * (1 - share) + float(ordered[high]) * share


def recommendation(band: str, percentile: float) -> tuple[str, str]:
    """文案一律相对口径：我们没校准，不能说「这是真正新的信息」。"""
    if band == BAND_HIGH:
        return (
            f"相对新颖：比 {percentile:.0f}% 的近期报道更新（前 25%）。",
            f"Relatively new: newer than {percentile:.0f}% of recent coverage (top 25%).",
        )
    if band == BAND_MID:
        return (
            f"中间档：比 {percentile:.0f}% 的近期报道更新，与既有报道可比。",
            f"Mid band: newer than {percentile:.0f}% of recent coverage.",
        )
    return (
        f"近期已覆盖：排在末 25%（比 {percentile:.0f}% 的近期报道更新）。",
        f"Recently covered: bottom 25% (newer than {percentile:.0f}% of recent coverage).",
    )


def age_days_between(moment: datetime, reference: datetime) -> float:
    """带符号的天数差，负值（未来时间）按 0 处理在调用侧完成。"""
    return (reference - moment).total_seconds() / 86400.0


def hours_between(earlier: datetime, later: datetime) -> float:
    """两个时刻的绝对间隔（小时）。"""
    return abs((later - earlier).total_seconds()) / 3600.0
