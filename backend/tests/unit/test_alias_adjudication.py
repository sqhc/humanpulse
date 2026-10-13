"""别名裁决：路由规则与报告汇总（不依赖数据库与判官）。"""

from __future__ import annotations

import asyncio
from typing import Any

from app.judgement import FakeJudgementClient, JudgementError
from app.pipeline.alias_adjudication import (
    DEFAULT_MERGE_THRESHOLD,
    DEFAULT_REVIEW_FLOOR,
    adjudicate_candidates,
    pairs_to_merge,
    route_verdict,
)


def test_route_verdict_thresholds() -> None:
    assert route_verdict(0.9) == "merge"
    assert route_verdict(DEFAULT_MERGE_THRESHOLD) == "merge"  # 边界含在内
    assert route_verdict(0.3) == "review"
    assert route_verdict(DEFAULT_REVIEW_FLOOR) == "review"
    assert route_verdict(0.05) == "reject"


def test_merge_threshold_is_below_scale_midpoint() -> None:
    """实测阈值必须低于量表名义中点。

    判官几乎不用最高档位（实测档位 2 从不出现），写死中点会让召回率掉到近 0——
    这正是上一轮踩过的坑（阈值 1.5 时召回率 0.009）。
    """
    assert DEFAULT_MERGE_THRESHOLD < 1.5
    assert 0 < DEFAULT_REVIEW_FLOOR < DEFAULT_MERGE_THRESHOLD


def _candidate(left: str, right: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "person",
        "left": {"id": 1, "name": left},
        "right": {"id": 2, "name": right},
        "shared_documents": 3,
        "jaccard": 0.7,
    }
    base.update(extra)
    return base


def test_adjudicate_with_fake_judge() -> None:
    candidates = [_candidate("China", "中国"), _candidate("Iran", "伊朗")]
    report = asyncio.run(
        adjudicate_candidates(None, candidates=candidates, client=FakeJudgementClient())  # type: ignore[arg-type]
    )
    assert report.candidates == 2
    assert report.provider == "fake"
    assert len(report.results) == 2
    # 每个结论都必须是三种动作之一，且计数自洽
    assert report.merged + report.review + report.rejected == 2
    assert all(item.verdict in {"merge", "review", "reject"} for item in report.results)


def test_adjudicate_isolates_failures() -> None:
    class FlakyJudge(FakeJudgementClient):
        async def ask(self, state, questions, *, model=None):  # type: ignore[no-untyped-def]
            if "坏数据" in state:
                raise JudgementError("模拟判官故障")
            return await super().ask(state, questions, model=model)

    candidates = [_candidate("China", "中国"), _candidate("坏数据", "broken")]
    report = asyncio.run(
        adjudicate_candidates(None, candidates=candidates, client=FlakyJudge())  # type: ignore[arg-type]
    )
    assert report.failed == 1
    assert len(report.results) == 1
    assert report.errors


def test_pairs_to_merge_only_includes_merges() -> None:
    from app.pipeline.alias_adjudication import Adjudication, AdjudicationReport

    report = AdjudicationReport(threshold=DEFAULT_MERGE_THRESHOLD)
    report.results = [
        Adjudication(
            kind="place",
            left_id=10,
            left_name="China",
            right_id=11,
            right_name="中国",
            score=0.9,
            confidence=0.8,
            verdict="merge",
        ),
        Adjudication(
            kind="place",
            left_id=20,
            left_name="Iran",
            right_id=21,
            right_name="伊拉克",
            score=0.1,
            confidence=0.5,
            verdict="reject",
        ),
    ]
    merges = pairs_to_merge(report)
    assert len(merges) == 1
    assert merges[0]["canonical_id"] == 10
    assert merges[0]["alias_ids"] == [11]
