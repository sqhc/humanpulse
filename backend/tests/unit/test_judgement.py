"""判官层：三种原语的转换、概率口径、以及假实现的确定性。

这些测试**不依赖 typesafe-sdk 与 torch**（CI 不装 judgement extra），
所以只能在纯逻辑层面钉住行为；真实模型的调用质量由评估门单独衡量。
"""

from __future__ import annotations

import asyncio

import pytest

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
from app.judgement.typesafe import answer_from_raw


def _run(coro):
    return asyncio.run(coro)


class _Raw:
    """鸭子类型的假 answer 对象，模拟 typesafe-sdk 的返回结构。"""

    def __init__(self, type_, **kwargs):
        self.type = type_
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_answer_from_raw_choice() -> None:
    raw = _Raw(
        "choice",
        choice="billing",
        confidence=0.71,
        probabilities={"billing": 0.8, "account": 0.2},
    )
    answer = answer_from_raw("category", raw)
    assert answer.kind == "choice"
    assert answer.choice == "billing"
    assert answer.probabilities == {"billing": 0.8, "account": 0.2}
    assert answer.confidence == pytest.approx(0.71)


def test_answer_from_raw_noul_has_no_confidence() -> None:
    answer = answer_from_raw("is_greeting", _Raw("noul", noul=0.31))
    assert answer.kind == "noul"
    assert answer.noul == pytest.approx(0.31)
    assert answer.confidence is None


def test_answer_from_raw_unknown_type_falls_back_to_noul() -> None:
    answer = answer_from_raw("weird", _Raw("banana", noul=0.5))
    assert answer.kind == "noul"


def test_probability_semantics() -> None:
    noul = JudgementAnswer(key="k", kind="noul", noul=0.42)
    assert noul.probability() == pytest.approx(0.42)

    # choice：取「选中项」的预测概率，而不是 confidence
    choice = JudgementAnswer(
        key="k",
        kind="choice",
        choice="b",
        probabilities={"a": 0.3, "b": 0.6, "c": 0.1},
        confidence=0.4,
    )
    assert choice.probability() == pytest.approx(0.6)

    # score：量表后半区间的概率质量（0..3 里取 2、3）
    score = JudgementAnswer(
        key="k",
        kind="score",
        score=1.8,
        probabilities={"0": 0.05, "1": 0.25, "2": 0.5, "3": 0.2},
    )
    assert score.probability() == pytest.approx(0.7)


def test_probability_handles_empty_distribution() -> None:
    assert JudgementAnswer(key="k", kind="score").probability() == 0.0
    assert JudgementAnswer(key="k", kind="choice").probability() == 0.0


def test_fake_judge_is_deterministic() -> None:
    client = FakeJudgementClient()
    questions = {
        "escalation": ScoreQuestion(
            instructions="升级程度？", criteria=("降温", "维持", "升级", "失控")
        ),
        "downstream": ChoiceQuestion(
            instructions="下游类型？", criteria={"经济": "经济", "军事": "军事"}
        ),
        "indicator": NoulQuestion(instructions="是否有先行指标？"),
    }
    first = _run(client.ask("同一段 state", questions))
    second = _run(client.ask("同一段 state", questions))
    assert first.answers == second.answers
    assert set(first.answers) == set(questions)


def test_fake_judge_noul_stays_in_range() -> None:
    client = FakeJudgementClient()
    for index in range(20):
        response = _run(client.ask(f"state-{index}", {"q": NoulQuestion(instructions="是非题")}))
        value = response.answers["q"].noul
        assert value is not None and 0.0 <= value < 1.0


def test_fake_judge_choice_is_a_valid_distribution() -> None:
    client = FakeJudgementClient()
    criteria = {"a": "甲", "b": "乙", "c": "丙"}
    response = _run(
        client.ask("某段 state", {"pick": ChoiceQuestion(instructions="选一个", criteria=criteria)})
    )
    answer = response.answers["pick"]
    assert answer.choice in criteria
    assert sum(answer.probabilities.values()) == pytest.approx(1.0, abs=0.01)
    # choice 必须与实际最大概率一致，否则probability()口径会与choice矛盾
    best = max(answer.probabilities, key=lambda option: answer.probabilities[option])
    assert answer.choice == best


def test_fake_judge_score_within_scale() -> None:
    client = FakeJudgementClient()
    response = _run(
        client.ask(
            "某段 state",
            {"s": ScoreQuestion(instructions="打分", criteria=("低", "中", "高"))},
        )
    )
    answer = response.answers["s"]
    assert answer.score is not None and 0.0 <= answer.score <= 2.0
    assert sum(answer.probabilities.values()) == pytest.approx(1.0, abs=0.01)


def test_fake_judge_differs_across_states() -> None:
    client = FakeJudgementClient()
    question = {"q": NoulQuestion(instructions="是非题")}
    a = _run(client.ask("state A", question)).answers["q"].noul
    b = _run(client.ask("state B", question)).answers["q"].noul
    assert a != b


def test_get_judgement_client_none_and_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    # get_settings 也是 lru_cache 的，setenv 后必须一起清，否则读到旧配置
    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "none")
    assert get_judgement_client() is None
    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "fake")
    client = get_judgement_client()
    assert isinstance(client, FakeJudgementClient)
    get_settings.cache_clear()
    get_judgement_client.cache_clear()


def test_get_judgement_client_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "nope")
    with pytest.raises(JudgementError):
        get_judgement_client()
    get_settings.cache_clear()
    get_judgement_client.cache_clear()
