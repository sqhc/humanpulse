"""推演链路：状态压缩、分支问题集、节点组装、失败隔离。

用假判官驱动，因此不依赖 Laya 权重与 typesafe-sdk（CI 可跑）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.briefs.projection import (
    DOWNSTREAM_TYPES,
    ESCALATION_SCALE_ZH,
    HOP2_CALM,
    HOP2_ESCALATING,
    build_event_state,
    build_hop1_questions,
    build_hop2_questions,
    build_hop3_questions,
    chain_from_responses,
    escalation_level,
    generate_projection,
)
from app.briefs.select import SelectedItem
from app.config import get_settings
from app.judgement import (
    ChoiceQuestion,
    FakeJudgementClient,
    JudgementAnswer,
    JudgementError,
    NoulQuestion,
    ScoreQuestion,
    get_judgement_client,
)


def _item(**kwargs) -> SelectedItem:
    base = {
        "document_id": 1,
        "cluster_id": 10,
        "title": "霍尔木兹海峡局势持续紧张",
        "summary_zh": "伊朗与美国在霍尔木兹海峡的对峙升级，双方均未让步。",
        "summary_en": "Iran and the US remain at loggerheads over the Strait of Hormuz.",
        "score": 82,
        "source_name": "Al Jazeera",
        "url": "https://example.test/a",
        "published_at": datetime(2026, 9, 27, tzinfo=UTC),
        "headline_only": False,
    }
    base.update(kwargs)
    return SelectedItem(**base)


# ---------- state 压缩 ----------


def test_build_event_state_includes_priority_blocks() -> None:
    state = build_event_state(_item())
    assert "事件：霍尔木兹海峡局势持续紧张" in state
    assert "中文摘要" in state
    assert "来源：Al Jazeera" in state
    assert "日期：2026-09-27" in state


def test_build_event_state_drops_low_priority_when_over_budget() -> None:
    long_summary = "很长的中文摘要。" * 100
    state = build_event_state(_item(summary_zh=long_summary, summary_en="x" * 100), max_chars=120)
    assert len(state) <= 120
    # 标题优先级最高，必须留下
    assert "霍尔木兹海峡局势持续紧张" in state
    # 低优先级的日期应该被丢掉，而不是把摘要腰斩后还硬塞日期
    assert "日期：" not in state


def test_build_event_state_never_truncates_below_minimum() -> None:
    state = build_event_state(_item(title="标题", summary_zh="摘要" * 200), max_chars=80)
    assert len(state) <= 80


# ---------- 问题集 ----------


def test_hop1_questions_have_three_primitives() -> None:
    questions = build_hop1_questions(horizon_days=14)
    assert isinstance(questions["escalation"], ScoreQuestion)
    assert isinstance(questions["downstream"], ChoiceQuestion)
    assert isinstance(questions["indicator"], NoulQuestion)
    assert len(questions["escalation"].criteria) == len(ESCALATION_SCALE_ZH)
    assert set(questions["downstream"].criteria) == set(DOWNSTREAM_TYPES)


def test_escalation_level_maps_score_to_scale() -> None:
    assert escalation_level(JudgementAnswer(key="e", kind="score", score=0.2)) == 0
    assert escalation_level(JudgementAnswer(key="e", kind="score", score=1.4)) == 1
    assert escalation_level(JudgementAnswer(key="e", kind="score", score=2.6)) == 3
    assert escalation_level(JudgementAnswer(key="e", kind="score", score=None)) == 0
    # 越界也要夹住
    assert escalation_level(JudgementAnswer(key="e", kind="score", score=99.0)) == 3


def test_hop2_branches_on_escalation() -> None:
    calm = build_hop2_questions(escalation=0, horizon_days=14)
    hot = build_hop2_questions(escalation=3, horizon_days=14)
    assert "negotiation" in calm and "negotiation" not in hot
    assert "direct_conflict" in hot and "direct_conflict" not in calm
    # 共同节点：两条分支都要问第三方调停，链路才有可比性
    assert "third_party" in calm and "third_party" in hot
    assert set(calm) == {key for key, _, _, _ in HOP2_CALM}
    assert set(hot) == {key for key, _, _, _ in HOP2_ESCALATING}


def test_hop3_has_horizon_question() -> None:
    assert "horizon_realized" in build_hop3_questions(horizon_days=30)


# ---------- 链路组装 ----------


def _answers(**kwargs) -> dict[str, JudgementAnswer]:
    base = {
        "escalation": JudgementAnswer(
            key="escalation",
            kind="score",
            score=2.4,
            probabilities={"0": 0.05, "1": 0.15, "2": 0.5, "3": 0.3},
            confidence=0.72,
        ),
        "downstream": JudgementAnswer(
            key="downstream",
            kind="choice",
            choice="military",
            probabilities={"military": 0.55, "economy": 0.3, "diplomacy": 0.15},
            confidence=0.66,
        ),
        "indicator": JudgementAnswer(key="indicator", kind="noul", noul=0.8),
        "direct_conflict": JudgementAnswer(key="direct_conflict", kind="noul", noul=0.42),
        "energy_shipping": JudgementAnswer(key="energy_shipping", kind="noul", noul=0.77),
        "third_party": JudgementAnswer(key="third_party", kind="noul", noul=0.61),
        "horizon_realized": JudgementAnswer(key="horizon_realized", kind="noul", noul=0.35),
    }
    base.update(kwargs)
    return base


def test_chain_nodes_follow_the_hops() -> None:
    chain = chain_from_responses(_item(), _answers(), horizon_days=14, min_confidence=0.6)
    kinds = [node.kind for node in chain.nodes]
    assert kinds[0] == "fact"
    assert "effect" in kinds
    assert "second_order" in kinds
    assert "counter" in kinds
    assert "indicator" in kinds
    assert kinds[-1] == "horizon"
    # 事实节点恒为 1.0，且带原文链接
    assert chain.nodes[0].probability == 1.0
    assert chain.nodes[0].evidence_urls == ["https://example.test/a"]
    hops = {node.hop for node in chain.nodes}
    assert hops == {0, 1, 2, 3}


def test_chain_marks_low_confidence_as_tentative() -> None:
    answers = _answers(
        escalation=JudgementAnswer(
            key="escalation", kind="score", score=2.4, probabilities={"2": 0.6}, confidence=0.31
        )
    )
    chain = chain_from_responses(_item(), answers, horizon_days=14, min_confidence=0.6)
    escalation_node = next(node for node in chain.nodes if node.label_zh == "冲突烈度")
    assert escalation_node.tentative is True
    # 待观察节点不应出现在「可断言」集合里
    assert escalation_node not in chain.asserted_nodes()


def test_chain_noul_nodes_are_not_tentative() -> None:
    # Noul 没有 confidence，不能因此被降级为待观察
    chain = chain_from_responses(_item(), _answers(), horizon_days=14, min_confidence=0.99)
    noul_nodes = [node for node in chain.nodes if node.confidence is None and node.kind != "fact"]
    assert noul_nodes
    assert all(not node.tentative for node in noul_nodes)


def test_chain_uses_calm_branch_when_escalation_low() -> None:
    answers = {
        "escalation": JudgementAnswer(key="escalation", kind="score", score=0.1, confidence=0.8),
        "negotiation": JudgementAnswer(key="negotiation", kind="noul", noul=0.7),
        "spillover": JudgementAnswer(key="spillover", kind="noul", noul=0.4),
        "third_party": JudgementAnswer(key="third_party", kind="noul", noul=0.5),
    }
    chain = chain_from_responses(_item(), answers, horizon_days=14, min_confidence=0.6)
    labels = {node.label_zh for node in chain.nodes}
    assert "谈判进展" in labels
    assert "直接冲突" not in labels


def test_chain_tolerates_missing_answers() -> None:
    chain = chain_from_responses(_item(), {}, horizon_days=14, min_confidence=0.6)
    # 最少也要有事实节点，不能抛异常
    assert [node.kind for node in chain.nodes] == ["fact"]


def test_indicators_only_when_probability_high() -> None:
    answers = _answers(indicator=JudgementAnswer(key="indicator", kind="noul", noul=0.2))
    chain = chain_from_responses(_item(), answers, horizon_days=14, min_confidence=0.6)
    assert chain.watch_indicators_zh == []


# ---------- 编排 ----------


def test_generate_projection_with_fake_judge() -> None:
    client = FakeJudgementClient()
    content = asyncio.run(
        generate_projection(
            [_item(document_id=1), _item(document_id=2, title="第二条事件")],
            horizon_days=14,
            max_events=2,
            hops=3,
            min_confidence=0.6,
            client=client,
        )
    )
    assert content is not None
    assert len(content.chains) == 2
    assert content.horizon_days == 14
    assert content.method["provider"] == "fake"
    assert content.method["calibrated"] is False
    # 未过评估门时必须如实标注
    assert any("未通过校准评估" in note for note in content.notes)
    assert all(chain.nodes for chain in content.chains)


def test_generate_projection_respects_max_events() -> None:
    client = FakeJudgementClient()
    items = [_item(document_id=index, title=f"事件 {index}") for index in range(1, 6)]
    content = asyncio.run(
        generate_projection(
            items, horizon_days=7, max_events=2, hops=1, min_confidence=0.6, client=client
        )
    )
    assert content is not None and len(content.chains) == 2


def test_generate_projection_returns_none_without_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "none")
    try:
        result = asyncio.run(
            generate_projection(
                [_item()], horizon_days=14, max_events=1, hops=1, min_confidence=0.6
            )
        )
        assert result is None
    finally:
        get_settings.cache_clear()
        get_judgement_client.cache_clear()


def test_generate_projection_isolates_failures() -> None:
    """一条链路失败不能让整期推演为空。"""

    class FlakyJudge(FakeJudgementClient):
        async def ask(self, state, questions, *, model=None):  # type: ignore[no-untyped-def]
            if "第二条" in state:
                raise JudgementError("模拟判官故障")
            return await super().ask(state, questions, model=model)

    content = asyncio.run(
        generate_projection(
            [_item(document_id=1), _item(document_id=2, title="第二条事件")],
            horizon_days=14,
            max_events=2,
            hops=1,
            min_confidence=0.6,
            client=FlakyJudge(),
        )
    )
    assert content is not None
    assert len(content.chains) == 1
    assert any("推演失败" in note for note in content.notes)
