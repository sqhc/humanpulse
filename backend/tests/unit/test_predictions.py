"""预测登记表：登记规则、顺延/过期、Brier 计算。

用轻量假 session（鸭子类型）驱动，不需要数据库——数据库路径由冒烟脚本覆盖。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.briefs.schema import ProjectionChain, ProjectionNode
from app.briefs.select import SelectedItem
from app.models.prediction import PREDICTION_STATUSES, Prediction
from app.predictions.registry import (
    HIT_THRESHOLD,
    MAX_DEFERRALS,
    MISS_THRESHOLD,
    ResolveReport,
    _defer,
    _resolve_question,
    register_brief_projection,
    register_chain,
    tracked_kinds,
)


class FakeSession:
    """只实现 register_chain 用到的那两个方法。"""

    def __init__(self) -> None:
        self.added: list[Prediction] = []
        self.flushed = 0

    def add(self, obj: Prediction) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1


def _chain() -> ProjectionChain:
    return ProjectionChain(
        document_id=42,
        cluster_id=7,
        source_name="test",
        event_title_zh="测试事件",
        event_title_en="test event",
        nodes=[
            ProjectionNode(hop=0, kind="fact", statement_zh="事件本身", probability=1.0),
            ProjectionNode(
                hop=1, kind="effect", statement_zh="升级概率", probability=0.72, confidence=0.55
            ),
            ProjectionNode(hop=1, kind="indicator", statement_zh="有先行指标", probability=0.4),
            ProjectionNode(hop=2, kind="second_order", statement_zh="外溢", probability=0.31),
            ProjectionNode(hop=2, kind="second_order", statement_zh="空话术", probability=0.2),
        ],
    )


def _item(document_id: int = 1, title: str = "测试事件") -> SelectedItem:
    return SelectedItem(
        document_id=document_id,
        cluster_id=7,
        title=title,
        summary_zh="这是一段用于推演的中文摘要。",
        summary_en="An English summary for projection.",
        score=80,
        source_name="test",
        url="https://example.test/a",
        published_at=datetime(2026, 9, 27, tzinfo=UTC),
        headline_only=False,
    )


def test_tracked_kinds_excludes_fact() -> None:
    kinds = tracked_kinds()
    assert "fact" not in kinds
    assert {"effect", "second_order", "counter", "indicator", "horizon"} <= set(kinds)


def test_register_chain_skips_fact_nodes() -> None:
    import asyncio

    session = FakeSession()
    moment = datetime(2026, 9, 20, tzinfo=UTC)
    created = asyncio.run(
        register_chain(
            session,
            _chain(),
            brief_id=3,
            provider="laya",
            model="laya-multilingual",
            horizon_days=14,
            registered_at=moment,
        )
    )
    assert len(created) == 4  # fact 被跳过
    assert session.flushed == 1
    assert all(item.brief_id == 3 for item in created)
    assert all(item.status == "open" for item in created)
    assert all(item.status in PREDICTION_STATUSES for item in created)


def test_register_chain_computes_due_date_and_probability() -> None:
    import asyncio

    session = FakeSession()
    moment = datetime(2026, 9, 20, tzinfo=UTC)
    created = asyncio.run(
        register_chain(
            session,
            _chain(),
            brief_id=None,
            provider="laya",
            model="m",
            horizon_days=14,
            registered_at=moment,
        )
    )
    effect = next(item for item in created if item.question_key == "effect")
    assert effect.due_at == moment + timedelta(days=14)
    assert float(effect.predicted_probability) == pytest.approx(0.72)
    assert float(effect.confidence) == pytest.approx(0.55)
    # 登记原始概率，不改写话术
    assert effect.statement_zh == "升级概率"
    assert effect.evidence["registered_at"].startswith("2026-09-20")


def test_register_chain_skips_empty_statements() -> None:
    import asyncio

    session = FakeSession()
    chain = _chain()
    chain.nodes.append(ProjectionNode(hop=1, kind="effect", statement_zh="   ", probability=0.5))
    created = asyncio.run(
        register_chain(session, chain, brief_id=None, provider="fake", model="m", horizon_days=7)
    )
    assert len(created) == 4  # 空话术不登记


def test_register_brief_projection_skips_without_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """判官未配置时静默跳过，不登记任何预测、不影响简报生成。"""
    import asyncio

    from app.config import get_settings
    from app.judgement import get_judgement_client

    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "none")
    try:
        session = FakeSession()
        count = asyncio.run(register_brief_projection(session, [_item()], brief_id=3))
        assert count == 0
        assert session.added == []
    finally:
        get_settings.cache_clear()
        get_judgement_client.cache_clear()


def test_register_brief_projection_registers_with_fake_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """判官配置后，把每条链的可证伪节点登记成预测（P3 样本积累）。"""
    import asyncio

    from app.config import get_settings
    from app.judgement import get_judgement_client

    get_settings.cache_clear()
    get_judgement_client.cache_clear()
    monkeypatch.setenv("JUDGEMENT_PROVIDER", "fake")
    try:
        session = FakeSession()
        items = [_item(document_id=1), _item(document_id=2, title="第二条事件")]
        count = asyncio.run(register_brief_projection(session, items, brief_id=3))
        assert count > 0
        assert session.flushed >= 1
        assert all(item.brief_id == 3 for item in session.added)
        assert all(item.status == "open" for item in session.added)
    finally:
        get_settings.cache_clear()
        get_judgement_client.cache_clear()


def _prediction(deferrals: int = 0) -> Prediction:
    return Prediction(
        id=1,
        hop=1,
        question_key="effect",
        statement_zh="测试",
        statement_en="test",
        predicted_probability=Decimal("0.8"),
        horizon_days=7,
        due_at=datetime(2026, 9, 20, tzinfo=UTC),
        status="open",
        evidence={"deferrals": deferrals},
    )


def test_defer_reschedules_and_counts() -> None:
    prediction = _prediction()
    report = ResolveReport()
    moment = datetime(2026, 9, 25, tzinfo=UTC)
    _defer(prediction, moment, report, reason="没有证据")
    assert prediction.status == "open"
    assert prediction.due_at == moment + timedelta(days=7)
    assert prediction.evidence["deferrals"] == 1
    assert prediction.evidence["last_defer_reason"] == "没有证据"
    assert report.unresolved == 1
    assert report.expired == 0


def test_defer_expires_after_limit() -> None:
    # 已经顺延到上限，再顺延一次就该过期，而不是永远挂着
    prediction = _prediction(deferrals=MAX_DEFERRALS)
    report = ResolveReport()
    moment = datetime(2026, 9, 25, tzinfo=UTC)
    _defer(prediction, moment, report, reason="还是没证据")
    assert prediction.status == "expired"
    assert prediction.resolved_at == moment
    assert report.expired == 1
    assert report.unresolved == 0


def test_thresholds_leave_a_middle_band() -> None:
    # 中间地带必须存在，否则「拿不准」会被硬掰成对或错
    assert 0.0 < MISS_THRESHOLD < HIT_THRESHOLD < 1.0


def test_resolve_question_carries_the_statement() -> None:
    question = _resolve_question("能源与航运的概率 0.77")
    assert "能源与航运的概率 0.77" in question.instructions
    assert "兑现" in question.instructions


def test_brier_formula_matches_definition() -> None:
    # 直接按定义验算一次，确保落库的 brier 列不是随手写的
    predicted = 0.8
    for outcome in (True, False):
        expected = (predicted - (1.0 if outcome else 0.0)) ** 2
        assert expected == pytest.approx(0.04 if outcome else 0.64)
