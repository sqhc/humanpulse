"""Signal：文档级 novelty（这篇是不是真正的新信息）。

设计原则（写进代码，便于审计）：
- 只吃确定性信号：向量近邻相似度、时间间隔、来源分布、时间新近度。**不碰任何概率模型输出**，
  因此与「判官概率未过评估门」的约束无关，也不构成一条新的未校准能力。
- 每个因子取值都在 [0,1]；数据缺失时该因子**不参与**加权（权重重新归一化），
  而不是静默填 0 或 1 —— 缺失会通过 `basis_zh` / `confidence=partial` 显式暴露。
- 阈值 0.65 / 0.35 是人工设定、尚未与人工标注对齐：响应里 `calibrated=False`，
  前端必须按「未经校准」呈现（见 docs/design-pulse-thread-signal-copy.md）。

因子定义（默认权重 w1..w4 = 0.4/0.2/0.2/0.2，Σw = 1）：

1. newness  = 1 - 时间窗内最大余弦相似度（无近邻记 1.0；无向量则缺席）
2. time_freshness = 1 - exp(-Δt/τ)，Δt = 与**最相似**近邻的发布时间间隔，τ = 48h
   （紧跟一篇几乎相同的报道 → 0；没有近邻 → 1）
3. source_diversity = 1 - 窗内同源占比（同一家源霸屏 → 低；多源覆盖 → 高）
4. recency = 1 - min(1, 距今天数/30)（今天 → 1；30 天前及更早 → 0）

注意：早期群里草案把 recency 写成 `min(1, 天数/30)`，方向是反的（越老越高）；这里已修正。
"""

from __future__ import annotations

import math
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

STATUS_NEW = "new"
STATUS_RELATED = "related"
STATUS_COVERED = "covered"

THRESHOLD_NEW = 0.65
THRESHOLD_RELATED = 0.35

NOTE_ZH = "novelty 阈值（0.65/0.35）与权重为人工设定，未与人工标注对齐：未经校准，仅供排序参考。"
NOTE_EN = (
    "Novelty thresholds (0.65/0.35) and weights are hand-set and not aligned with human labels: "
    "uncalibrated, for ranking only."
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

    @property
    def contribution(self) -> float:
        return 0.0 if self.value is None else self.value * self.weight


@dataclass(frozen=True)
class NoveltyScore:
    score: float
    status: str
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
    )


def source_diversity_factor(same_source: int | None, total: int | None) -> NoveltyFactor:
    """1 - 窗内同源占比。total=0 时该因子缺席（不猜）。"""
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
    )


def status_of(
    score: float, new_at: float = THRESHOLD_NEW, related_at: float = THRESHOLD_RELATED
) -> str:
    if score >= new_at:
        return STATUS_NEW
    if score >= related_at:
        return STATUS_RELATED
    return STATUS_COVERED


def compute_novelty(
    *,
    max_similarity: float | None,
    nearest_hours: float | None,
    same_source: int | None,
    total_in_window: int | None,
    age_days: float | None,
    has_embedding: bool,
    tau_hours: float = TAU_HOURS,
) -> NoveltyScore:
    """四因子加权。缺席因子不参与，权重重新归一化（不会凭空造一个 0.5）。"""
    factors: list[NoveltyFactor] = []
    basis_zh: list[str] = []
    basis_en: list[str] = []

    if has_embedding:
        factors.append(newness_factor(max_similarity))
        factors.append(time_freshness_factor(nearest_hours, tau_hours))
    else:
        basis_zh.append(MISSING_EMBEDDING_ZH)
        basis_en.append(MISSING_EMBEDDING_EN)
    factors.append(source_diversity_factor(same_source, total_in_window))
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
        status=status_of(score),
        factors=factors,
        basis_zh=basis_zh,
        basis_en=basis_en,
        confidence="partial" if metadata_only else "full",
    )


def recommendation(status: str, horizon_days: int) -> tuple[str, str]:
    if status == STATUS_NEW:
        return (
            f"重点看：近 {horizon_days} 天内没有高相似报道，可能是新信号。",
            f"Read first: no highly similar report in the last {horizon_days} days.",
        )
    if status == STATUS_RELATED:
        return (
            "可略读：与既有报道高度相关，先看已有脉络。",
            "Skim: closely related to existing coverage; start from the earlier thread.",
        )
    return (
        "可跳过：这条在窗口内已被更早的报道覆盖。",
        "Skip: already covered earlier inside the window.",
    )


def age_days_between(moment: datetime, reference: datetime) -> float:
    """带符号的天数差，负值（未来时间）按 0 处理在调用侧完成。"""
    return (reference - moment).total_seconds() / 86400.0


def hours_between(earlier: datetime, later: datetime) -> float:
    """两个时刻的绝对间隔（小时）。"""
    return abs((later - earlier).total_seconds()) / 3600.0
