"""实体对齐评估：指标、AUC、阈值选择、切分。

金标准来自人工别名表，所以这些函数的正确性直接影响「模型能不能用」的判断。
"""

from __future__ import annotations

import pytest

from app.eval.alignment import (
    ALIGNMENT_SCALE,
    ALIGNMENT_THRESHOLD,
    AlignmentReport,
    Pair,
    alignment_question,
    build_prompt,
    calibrate_scored,
    choose_threshold,
    decide,
    in_calibration,
    pairs_from_alias_groups,
    roc_auc,
    score_pairs,
    split_pairs,
    split_scored,
)
from app.pipeline.aliases import AliasGroup


def test_decide_uses_threshold() -> None:
    assert decide(2.0) is True
    assert decide(1.5) is True  # 恰好等于阈值算同一
    assert decide(1.4) is False
    assert decide(None) is False


def test_scale_has_three_levels() -> None:
    assert len(ALIGNMENT_SCALE) == 3
    # 顺序必须是从「不同」到「同一」，否则 score 的大小就没有意义
    assert "不同" in ALIGNMENT_SCALE[0]
    assert "同一个实体" in ALIGNMENT_SCALE[2]


def test_alignment_question_is_score_type() -> None:
    question = alignment_question()
    assert len(question.criteria) == len(ALIGNMENT_SCALE)


def test_build_prompt_includes_names_and_context() -> None:
    pair = Pair(
        left="China", right="中国", label=True, left_context="标题 A", right_context="标题 B"
    )
    prompt = build_prompt(pair)
    assert "China" in prompt and "中国" in prompt
    assert "标题 A" in prompt and "标题 B" in prompt


def test_build_prompt_without_context() -> None:
    prompt = build_prompt(Pair(left="A", right="B", label=False))
    assert "实体 A：A" in prompt
    assert "上下文" not in prompt


def test_pairs_from_alias_groups_labels_positives_and_negatives() -> None:
    groups = [
        AliasGroup("China", "place", ("中国", "PRC")),
        AliasGroup("Iran", "place", ("伊朗",)),
    ]
    pairs = pairs_from_alias_groups(groups, max_negatives=100)
    positives = {frozenset((p.left, p.right)) for p in pairs if p.label}
    negatives = {frozenset((p.left, p.right)) for p in pairs if not p.label}
    # 组内两两都是正样本
    assert frozenset(("China", "中国")) in positives
    assert frozenset(("中国", "PRC")) in positives
    # 跨组是负样本
    assert frozenset(("China", "Iran")) in negatives
    # 正负不能重叠
    assert not (positives & negatives)


def test_pairs_caps_negatives() -> None:
    groups = [AliasGroup(f"E{index}", "org", (f"A{index}",)) for index in range(20)]
    pairs = pairs_from_alias_groups(groups, max_negatives=5)
    negatives = [p for p in pairs if not p.label]
    # 负样本不设上限会让「准确率」失去意义（全判负就是高分）
    assert len(negatives) == 5


def test_roc_auc_perfect_and_random() -> None:
    perfect = [
        (Pair("a", "b", True), 0.9),
        (Pair("c", "d", True), 0.8),
        (Pair("e", "f", False), 0.2),
        (Pair("g", "h", False), 0.1),
    ]
    assert roc_auc(perfect) == pytest.approx(1.0)

    inverted = [(pair, 1.0 - score) for pair, score in perfect]
    assert roc_auc(inverted) == pytest.approx(0.0)

    # 所有分数相同的并列 -> 0.5（随机）
    tied = [(pair, 0.5) for pair, _ in perfect]
    assert roc_auc(tied) == pytest.approx(0.5)


def test_roc_auc_uses_rank_not_absolute_scale() -> None:
    """把全部分数整体压低，AUC 不应改变——这正是我们要的性质。

    实测判官把三档量表压缩到很窄的区间，任何绝对阈值都不稳；
    AUC 只关心排序，所以不受影响。
    """
    pairs = [
        (Pair("a", "b", True), 2.0),
        (Pair("c", "d", True), 1.5),
        (Pair("e", "f", False), 1.0),
        (Pair("g", "h", False), 0.5),
    ]
    shifted = [(pair, score * 0.2) for pair, score in pairs]
    assert roc_auc(pairs) == pytest.approx(roc_auc(shifted))


def test_roc_auc_handles_empty_and_single_class() -> None:
    assert roc_auc([]) == 0.0
    assert roc_auc([(Pair("a", "b", True), 0.9)]) == 0.0


def test_score_pairs_confusion_matrix() -> None:
    scored = [
        (Pair("a", "b", True), True),  # TP
        (Pair("c", "d", True), False),  # FN
        (Pair("e", "f", False), True),  # FP
        (Pair("g", "h", False), False),  # TN
    ]
    metrics = score_pairs(scored).as_dict()
    assert metrics["true_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["true_negative"] == 1
    assert metrics["accuracy"] == pytest.approx(0.5)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)


def test_choose_threshold_maximizes_f1_on_given_data() -> None:
    scored = [
        (Pair("a", "b", True), 0.9),
        (Pair("c", "d", True), 0.8),
        (Pair("e", "f", False), 0.3),
        (Pair("g", "h", False), 0.2),
    ]
    threshold = choose_threshold(scored)
    # 0.8 与 0.3 之间任何值都能分开；选出的阈值必须真的能分开
    assert 0.3 < threshold <= 0.8
    metrics = score_pairs([(pair, score >= threshold) for pair, score in scored])
    assert metrics.f1 == pytest.approx(1.0)


def test_choose_threshold_handles_empty() -> None:
    assert choose_threshold([]) == ALIGNMENT_THRESHOLD


def test_split_pairs_is_disjoint_and_deterministic() -> None:
    pairs = [Pair(f"L{i}", f"R{i}", label=i % 2 == 0) for i in range(200)]
    first_left, first_right = split_pairs(pairs)
    second_left, second_right = split_pairs(pairs)
    assert [p.left for p in first_left] == [p.left for p in second_left]
    assert [p.left for p in first_right] == [p.left for p in second_right]

    left_keys = {p.left + p.right for p in first_left}
    right_keys = {p.left + p.right for p in first_right}
    assert not (left_keys & right_keys)
    assert len(left_keys) + len(right_keys) == 200


def _compressed_sample(count: int = 200) -> list[tuple[Pair, float]]:
    """判官把量表压到低档时的典型样本：正样本 0.9、负样本 0.2，且正样本占多数（同真实金标准）。"""
    scored: list[tuple[Pair, float]] = []
    for index in range(count):
        label = index % 4 != 0
        scored.append((Pair(f"L{index}", f"R{index}", label), 0.9 if label else 0.2))
    return scored


def test_in_calibration_ignores_context() -> None:
    """切分键只用 left|right：带不带 context 必须落在同一侧。

    曾经用 `pair in calibration_set` 做成员判断，而 enriched 的 Pair 带 context、
    按值比较永远不相等，校准集因此整个落空（阈值静默回落到名义值）。
    """
    plain = Pair("China", "中国", True)
    enriched = Pair("China", "中国", True, left_context="标题 A", right_context="标题 B")
    assert in_calibration(plain) == in_calibration(enriched)


def test_split_scored_matches_split_pairs_and_keeps_everything() -> None:
    scored = _compressed_sample(120)
    calibration, test = split_scored(scored)
    left, right = split_pairs([pair for pair, _ in scored])
    assert [pair.left for pair, _ in calibration] == [pair.left for pair in left]
    assert [pair.left for pair, _ in test] == [pair.left for pair in right]
    assert len(calibration) + len(test) == len(scored)


def test_calibrate_scored_recovers_compressed_scale() -> None:
    """名义阈值下召回为 0，校准段却仍然可用——这个假象正是要防的误读。"""
    scored = _compressed_sample()
    nominal = score_pairs([(pair, decide(score)) for pair, score in scored])
    assert nominal.recall == pytest.approx(0.0)
    assert nominal.accuracy < nominal.majority_accuracy

    report = calibrate_scored(scored)
    assert report.calibration_size + report.test_metrics.sample_size == len(scored)
    assert report.test_metrics.positives > 0
    assert report.test_metrics.negatives > 0
    assert report.test_metrics.f1 == pytest.approx(1.0)
    assert 0.2 <= report.threshold <= 0.9


def test_calibrate_scored_threshold_depends_only_on_calibration_set() -> None:
    """把测试集的分数整体破坏，阈值必须不变、只有测试集报告变差。"""
    scored = _compressed_sample()
    first = calibrate_scored(scored)
    broken = [
        (pair, score) if in_calibration(pair) else (pair, 0.2 if pair.label else 0.9)
        for pair, score in scored
    ]
    second = calibrate_scored(broken)
    assert second.threshold == pytest.approx(first.threshold)
    assert second.test_metrics.f1 == pytest.approx(0.0)


def test_calibrate_scored_handles_empty() -> None:
    report = calibrate_scored([])
    assert report.threshold == ALIGNMENT_THRESHOLD
    assert report.calibration_size == 0
    assert report.test_metrics.sample_size == 0


def test_report_exposes_threshold_free_fields() -> None:
    report = AlignmentReport(provider="fake", auc=0.8)
    payload = report.as_dict()
    assert payload["auc"] == 0.8
    assert payload["decision_threshold"] == ALIGNMENT_THRESHOLD
    assert payload["calibrated"]["threshold"] == ALIGNMENT_THRESHOLD
    assert payload["calibrated"]["test_size"] == 0
