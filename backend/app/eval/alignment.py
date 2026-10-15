"""实体对齐裁决的分类评估：用人工别名表当金标准。

为什么这个评估比之前的覆盖预测更可信：
- **标签是人工做的**（backend/app/entity_aliases.yaml 的 31 个组，由人逐条核对），
  不是模型生成的。所以「模型与标签一致」等于「模型判对了」，而不是「两个模型互相同意」。
- 二分类任务（同一实体 / 不同实体），有明确的正负样本，能用准确率、
  精确率/召回率、以及基率衡量。不需要依赖概率校准是否精确——
  分类只要求相对排序正确（这与覆盖预测的失败模式形成对照）。

任务设计（直接复用 cookbook 第 4 章「实体对齐」的配方）：
- Score 三档：不同实体 / 相关但未必同一 / 完全同一
- 代码根据 Score 路由（>= 1.5 判同一），**不由模型决定动作**

**报告里为什么必须有 auc 与 calibrated**：1.5 是量表中点，但判官会把三档压到
很窄的区间（最高档常常不出现），于是同一个模型可能排序良好、在名义阈值下却
几乎全判「不同」。只看名义阈值下的准确率会把「量纲偏了」误读成「模型不可用」，
所以 `make eval-alignment` 同时给出阈值无关的 `auc`，以及「在校准集上选阈值、
在锁定测试集上报指标」的 `calibrated` 段。
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.judgement import JudgementClient, JudgementError, ScoreQuestion, get_judgement_client
from app.pipeline.aliases import AliasGroup, load_alias_groups

log = structlog.get_logger("eval.alignment")

# 三档量表：顺序即大小，代码按 1.5 阈值路由
ALIGNMENT_SCALE = (
    "两个不同的实体（不同国家/机构/人物）",
    "相关但未必是同一个实体（例如同一组织的不同部门）",
    "完全同一个实体（只是写法、语言或简称不同）",
)
ALIGNMENT_THRESHOLD = 1.5

ALIGNMENT_INSTRUCTIONS = (
    "下面给出两个实体名称及其上下文，请判断它们在现实世界中是否是同一个实体。"
    "请只根据名称本身判断，不要因为两者都涉及同一领域就判定为同一实体。"
)


@dataclass(frozen=True, slots=True)
class Pair:
    """一对待判断的实体（recall 阶段的候选）。"""

    left: str
    right: str
    label: bool  # True = 人工表中确认是同一实体
    left_context: str = ""
    right_context: str = ""


def build_prompt(pair: Pair) -> str:
    """把一对实体拼成 state（纯函数，便于单测）。"""
    lines = [
        "实体 A：" + pair.left,
        "实体 B：" + pair.right,
    ]
    if pair.left_context:
        lines.append("A 的上下文：" + pair.left_context[:160])
    if pair.right_context:
        lines.append("B 的上下文：" + pair.right_context[:160])
    return chr(10).join(lines)


def alignment_question() -> ScoreQuestion:
    return ScoreQuestion(instructions=ALIGNMENT_INSTRUCTIONS, criteria=ALIGNMENT_SCALE)


def decide(score: float | None, *, threshold: float = ALIGNMENT_THRESHOLD) -> bool:
    """代码根据 Score 决定「是否同一实体」——模型只回答语义问题。"""
    return (score or 0.0) >= threshold


@dataclass(slots=True)
class AlignmentMetrics:
    sample_size: int = 0
    positives: int = 0
    negatives: int = 0
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    failures: int = 0

    @property
    def base_rate(self) -> float:
        return self.positives / self.sample_size if self.sample_size else 0.0

    @property
    def accuracy(self) -> float:
        if not self.sample_size:
            return 0.0
        return (self.true_positive + self.true_negative) / self.sample_size

    @property
    def majority_accuracy(self) -> float:
        """基线：永远判「不同实体」（多数类）。"""
        return max(self.base_rate, 1.0 - self.base_rate)

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        if not (self.precision + self.recall):
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_size": self.sample_size,
            "positives": self.positives,
            "negatives": self.negatives,
            "base_rate": round(self.base_rate, 4),
            "accuracy": round(self.accuracy, 4),
            "majority_accuracy": round(self.majority_accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "failures": self.failures,
        }


def score_pairs(pairs: Sequence[tuple[Pair, bool]]) -> AlignmentMetrics:
    """把 (pair, 模型判定) 汇总成指标（纯函数）。"""
    metrics = AlignmentMetrics()
    for pair, predicted in pairs:
        metrics.sample_size += 1
        if pair.label:
            metrics.positives += 1
        else:
            metrics.negatives += 1
        if predicted and pair.label:
            metrics.true_positive += 1
        elif predicted and not pair.label:
            metrics.false_positive += 1
        elif not predicted and pair.label:
            metrics.false_negative += 1
        else:
            metrics.true_negative += 1
    return metrics


@dataclass(slots=True)
class CalibrationReport:
    """锁定测试集上的指标：阈值只在**校准集**上选，不许看测试集。"""

    threshold: float = ALIGNMENT_THRESHOLD
    calibration_size: int = 0
    test_metrics: AlignmentMetrics = field(default_factory=AlignmentMetrics)

    def as_dict(self) -> dict[str, object]:
        return {
            "threshold": round(self.threshold, 4),
            "calibration_size": self.calibration_size,
            "test_size": self.test_metrics.sample_size,
            "test_metrics": self.test_metrics.as_dict(),
        }


@dataclass(slots=True)
class AlignmentReport:
    provider: str = ""
    model: str = ""
    metrics: AlignmentMetrics = field(default_factory=AlignmentMetrics)
    errors: list[dict[str, str]] = field(default_factory=list)
    passed: bool = False
    verdict: str = ""
    limitations: list[str] = field(default_factory=list)
    # 上面 metrics 是**名义阈值**（ALIGNMENT_THRESHOLD）下的结果，会被量表压缩惩罚；
    # 判断「模型能不能用」要看 auc（阈值无关）与 calibrated（校准阈值 + 锁定测试集）。
    decision_threshold: float = ALIGNMENT_THRESHOLD
    auc: float = 0.0
    calibrated: CalibrationReport = field(default_factory=CalibrationReport)
    used_context: bool = False

    def as_dict(self) -> dict[str, object]:
        base: dict[str, object] = {
            "provider": self.provider,
            "model": self.model,
            "metrics": self.metrics.as_dict(),
            "decision_threshold": self.decision_threshold,
            "auc": round(self.auc, 4),
            "calibrated": self.calibrated.as_dict(),
            "used_context": self.used_context,
            "errors": self.errors,
            "passed": self.passed,
            "verdict": self.verdict,
            "limitations": self.limitations,
        }
        return base


def pairs_from_alias_groups(
    groups: Sequence[AliasGroup],
    *,
    include_negatives: bool = True,
    max_negatives: int = 60,
) -> list[Pair]:
    """从人工别名表构造标注对（纯函数）。

    正样本：同一组内 canonical 与每个 alias、以及 alias 两两之间——
    都是人工确认过的「同一个实体」，且多为跨语言/简繁/缩写。
    负样本：不同组的 canonical 两两配对——人工已确认它们是不同实体。

    负样本最多取 max_negatives 对：正样本本来就只有几十对，
    让负样本压倒性地多会让「准确率」变得毫无意义（全判负就是高分）。
    """
    pairs: list[Pair] = []
    for group in groups:
        names = [group.canonical, *group.aliases]
        for left, right in combinations(names, 2):
            pairs.append(Pair(left=left, right=right, label=True))
    if include_negatives:
        canonicals = [group.canonical for group in groups]
        negatives: list[Pair] = []
        for left, right in combinations(canonicals, 2):
            negatives.append(Pair(left=left, right=right, label=False))
        # 稳定取样（按名称排序后均匀取），保证可复现
        negatives.sort(key=lambda pair: (pair.left, pair.right))
        if len(negatives) > max_negatives:
            step = len(negatives) / max_negatives
            negatives = [negatives[int(index * step)] for index in range(max_negatives)]
        pairs.extend(negatives)
    return pairs


async def _contexts(
    session: AsyncSession, names: Sequence[str], *, limit: int = 1
) -> dict[str, str]:
    """给实体名取一段上下文（最近一次相关报道标题），帮助判官判断。"""
    if not names:
        return {}
    rows = (
        await session.execute(
            text(
                """
                select e.name, d.title
                from entities e
                join entity_mentions em on em.entity_id = e.id
                join documents d on d.id = em.document_id
                where e.name = any(:names)
                order by e.name, d.published_at desc
                """
            ),
            {"names": list(names)},
        )
    ).all()
    contexts: dict[str, str] = {}
    for name, title in rows:
        if name not in contexts:
            contexts[str(name)] = str(title or "")
    return contexts


async def run_alignment_eval(
    session: AsyncSession | None = None,
    *,
    limit: int | None = None,
    client: JudgementClient | None = None,
    groups: Sequence[AliasGroup] | None = None,
    use_context: bool = False,
) -> AlignmentReport:
    """用人工别名表评估判官的实体对齐能力。

    默认**不带**入库标题 context：2026-10-15 实测（同一 60 对，正负各 30）显示，
    把每边的最近报道标题塞进 prompt 会让 Laya 的排序反转——
    不带 context AUC 0.809，带 context 0.172（换措辞/加指令只到 0.317/0.378，救不回来）；
    而且生产路径 `app/pipeline/alias_adjudication.py` 本来就只拿名称问判官
    （`_as_pair` 不填 context）。**评估必须复现生产口径**，否则测出来的不是模型能力。
    `use_context=True` 保留给「想知道 context 有没有害」的实验，报告里会有标注。
    """
    judge = client or get_judgement_client()
    if judge is None:
        raise JudgementError("未配置判官（JUDGEMENT_PROVIDER=none），无法评估")

    alias_groups = list(groups) if groups is not None else load_alias_groups()
    pairs = pairs_from_alias_groups(alias_groups)
    if limit:
        pairs = pairs[:limit]
    if not pairs:
        raise JudgementError("人工别名表里没有可用的标注对")

    contexts: dict[str, str] = {}
    if use_context:
        if session is None:
            raise JudgementError("use_context=True 需要数据库会话")
        all_names = sorted({pair.left for pair in pairs} | {pair.right for pair in pairs})
        contexts = await _contexts(session, all_names)
    question = alignment_question()

    report = AlignmentReport()
    report.provider = judge.provider
    report.used_context = use_context
    # 只存原始分数：名义阈值、AUC、校准段都从这一份推出来，避免三处各判一次
    scored_raw: list[tuple[Pair, float]] = []
    for pair in pairs:
        enriched = Pair(
            left=pair.left,
            right=pair.right,
            label=pair.label,
            left_context=contexts.get(pair.left, ""),
            right_context=contexts.get(pair.right, ""),
        )
        try:
            response = await judge.ask(build_prompt(enriched), {"same_entity": question})
        except JudgementError as exc:
            report.metrics.failures += 1
            report.errors.append({"pair": pair.left + " ~ " + pair.right, "error": str(exc)[:120]})
            continue
        report.model = response.model or report.model
        answer = response.answers.get("same_entity")
        if answer is None:
            report.metrics.failures += 1
            continue
        scored_raw.append((enriched, float(answer.score or 0.0)))

    report.metrics = score_pairs([(pair, decide(score)) for pair, score in scored_raw])
    report.auc = round(roc_auc(scored_raw), 4)
    report.calibrated = calibrate_scored(scored_raw)
    report.limitations = [
        "金标准只有 31 组人工别名，正样本几十对、负样本采样 60 对，样本量小；",
        "负样本是不同国家的常见实体（容易），没有覆盖「同名不同实体」这类真正困难的情况；",
        "只评估「判断是否同一实体」这一步，不含召回（候选发现）的质量。",
        f"metrics 是名义阈值 {report.decision_threshold} 下的结果，会被量表压缩惩罚"
        "（判官几乎不使用最高档位）；判断能力请看 auc 与 calibrated（校准阈值 + 锁定测试集）。",
        "本次评估"
        + ("带" if use_context else "不带")
        + "入库标题 context；带 context 实测会把 Laya 的排序反转（AUC 0.809 → 0.172），"
        "生产别名裁决只按名称提问，所以默认不带。",
    ]
    metrics = report.metrics
    calibrated = report.calibrated
    # 阈值无关的证据必须进 verdict：只看名义阈值下的准确率会把「量纲偏了」误读成「不可用」
    evidence = (
        f"AUC {report.auc:.3f}（阈值无关）；校准阈值 {calibrated.threshold:.3f} 下"
        f"锁定测试集 F1 {calibrated.test_metrics.f1:.3f}"
    )
    if metrics.sample_size and metrics.accuracy > metrics.majority_accuracy + 0.1:
        report.passed = True
        report.verdict = (
            f"通过：准确率 {metrics.accuracy:.3f} 明显高于多数类基线 "
            f"{metrics.majority_accuracy:.3f}（F1 {metrics.f1:.3f}）；{evidence}"
        )
    else:
        report.passed = False
        report.verdict = (
            f"未通过：准确率 {metrics.accuracy:.3f} 未明显高于多数类基线 "
            f"{metrics.majority_accuracy:.3f}；{evidence}"
        )

    return report


def roc_auc(pairs: Sequence[tuple[Pair, float]]) -> float:
    """ROC AUC：只衡量「正样本得分是否排在负样本之上」，不需要选阈值。

    为什么必须要这个指标：
    实测发现判官把三档量表压缩到很窄的区间（正样本均值 0.89、负样本 0.63，
    档位 2 从不出现），所以任何绝对值阈值都不稳。
    但只要排序正确，我们就能**自己**选阈值——这正是「分类可用而概率不可用」的含义。
    AUC 0.5 = 随机，1.0 = 完美排序。
    """
    positives = [score for pair, score in pairs if pair.label]
    negatives = [score for pair, score in pairs if not pair.label]
    if not positives or not negatives:
        return 0.0
    # 用秩和公式（Mann-Whitney U），并列分数算 0.5
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def choose_threshold(pairs: Sequence[tuple[Pair, float]], *, metric: str = "f1") -> float:
    """在给定数据上选使 F1 最大的阈值（**只能在校准集上调用**）。"""
    if not pairs:
        return ALIGNMENT_THRESHOLD
    candidates = sorted({score for _, score in pairs})
    best_threshold = candidates[0]
    best_value = -1.0
    for candidate in candidates:
        predicted = [(pair, score >= candidate) for pair, score in pairs]
        metrics = score_pairs(predicted)
        value = metrics.f1 if metric == "f1" else metrics.accuracy
        if value > best_value:
            best_value = value
            best_threshold = candidate
    return best_threshold


def pair_key(pair: Pair) -> str:
    """切分键：只用实体名对，不受 context 影响。"""
    return pair.left + "|" + pair.right


def in_calibration(pair: Pair, *, ratio: float = 0.5) -> bool:
    """稳定地把一对分到校准集（True）或锁定测试集（False）。

    用哈希而不是随机：同一对每次都在同一侧，报告可复现。
    键只用 `left|right`，所以带不带 context 的同一个 Pair 一定落在同一侧。
    """
    digest = hashlib.blake2b(pair_key(pair).encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 10_000 < int(ratio * 10_000)


def split_pairs(pairs: Sequence[Pair], *, ratio: float = 0.5) -> tuple[list[Pair], list[Pair]]:
    """按实体名稳定切分，保证同一对不会同时出现在两边。"""
    left = [pair for pair in pairs if in_calibration(pair, ratio=ratio)]
    right = [pair for pair in pairs if not in_calibration(pair, ratio=ratio)]
    return left, right


def split_scored(
    pairs: Sequence[tuple[Pair, float]], *, ratio: float = 0.5
) -> tuple[list[tuple[Pair, float]], list[tuple[Pair, float]]]:
    """与 `split_pairs` 同一套切分，但保留分数（评估回写时用这个）。"""
    calibration: list[tuple[Pair, float]] = []
    test: list[tuple[Pair, float]] = []
    for pair, score in pairs:
        (calibration if in_calibration(pair, ratio=ratio) else test).append((pair, score))
    return calibration, test


def calibrate_scored(
    pairs: Sequence[tuple[Pair, float]], *, ratio: float = 0.5, metric: str = "f1"
) -> CalibrationReport:
    """在校准集上选阈值，只在锁定测试集上报指标（阈值不许看测试集）。

    为什么必须有这一段：名义阈值 1.5 是量表中点，判官却常把分数压在低档，
    于是同一个模型在名义阈值下召回≈0（被误读成「不可用」），排序其实可用。
    """
    calibration, test = split_scored(pairs, ratio=ratio)
    threshold = choose_threshold(calibration, metric=metric)
    predicted = [(pair, decide(score, threshold=threshold)) for pair, score in test]
    return CalibrationReport(
        threshold=threshold,
        calibration_size=len(calibration),
        test_metrics=score_pairs(predicted),
    )
