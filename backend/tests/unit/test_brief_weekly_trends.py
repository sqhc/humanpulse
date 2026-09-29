"""周报的趋势统计：排序与提示词文本都必须是纯函数、可断言。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.weekly import WeeklyTrends, format_trends, rank_tag_deltas


def test_rank_tag_deltas_prefers_new_and_fast_growing_tags() -> None:
    current = {"conflict": 10, "science": 5, "labor": 3, "olds": 4}
    previous = {"conflict": 6, "science": 5, "labor": 3, "olds": 9}
    ranked = rank_tag_deltas(current, previous)
    assert ranked[0] == ("conflict", 10, 6)
    assert ("labor", 3, 3) in ranked
    # 下降的话题排最后
    assert ranked[-1][0] == "olds"


def test_rank_tag_deltas_respects_limit() -> None:
    current = {f"tag{i}": i for i in range(10)}
    assert len(rank_tag_deltas(current, {})) == 6
    assert len(rank_tag_deltas(current, {}, limit=2)) == 2


def test_new_tag_counts_as_zero_previous() -> None:
    ranked = rank_tag_deltas({"brand-new": 4}, {})
    assert ranked == [("brand-new", 4, 0)]


def trends() -> WeeklyTrends:
    return WeeklyTrends(
        period_start=datetime(2026, 9, 21, tzinfo=UTC),
        period_end=datetime(2026, 9, 27, tzinfo=UTC),
        documents=323,
        sources=18,
        languages={"zh": 120, "en": 203},
        rising_tags=[("conflict", 40, 12), ("ai", 18, 5)],
        top_tags=[("conflict", 40), ("science", 22)],
        top_regions=[("asia", 30), ("europe", 12)],
        new_clusters=305,
        multi_source_clusters=10,
        biggest_clusters=[(573, 6, ["south africa", "shooting", "gun violence"])],
        headline_only_ratio=0.14,
    )


def test_format_trends_includes_all_computed_numbers() -> None:
    text = format_trends(trends())
    assert "323 条" in text
    assert "18 个来源" in text
    assert "conflict(40)" in text
    assert "conflict(本周40/上周12)" in text
    assert "asia(30)" in text
    assert "本周新增 305 个" in text
    assert "10 个由多个来源共同报道" in text
    assert "cluster#573" in text
    assert "south africa" in text
    assert "14%" in text


def test_format_trends_handles_empty_data() -> None:
    empty = WeeklyTrends(
        period_start=datetime(2026, 9, 21, tzinfo=UTC),
        period_end=datetime(2026, 9, 27, tzinfo=UTC),
    )
    text = format_trends(empty)
    assert "0 条" in text
    assert "本周新增 0 个" in text
    assert "%" not in text
