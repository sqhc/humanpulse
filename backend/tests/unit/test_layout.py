"""版式与配色：纯布局计算（不需要 Pillow）。

渲染本身靠抽帧目视与 E2E 冒烟验证；这里钉住的是容易写错又不容易看出来的几何逻辑——
两列排布、自适应缩放的选值、tab 高亮定位。
"""

from __future__ import annotations

import pytest

from app.video.layout import column_positions, fit_scale, total_height
from app.video.theme import DARK, LIGHT, get_theme

# ---------- 主题 ----------


def test_get_theme_defaults_to_light() -> None:
    assert get_theme(None) is LIGHT
    assert get_theme("") is LIGHT
    assert get_theme("light") is LIGHT
    assert get_theme("dark") is DARK
    # 未知名字回退到浅色，而不是抛异常让整片渲染失败
    assert get_theme("neon") is LIGHT


def test_themes_have_distinct_pages() -> None:
    assert LIGHT.page != DARK.page
    assert LIGHT.accent != DARK.accent


def test_light_palette_matches_sampled_screenshot() -> None:
    # 这三个值是直接从排版参考截屏采样出来的，改动要是有意为之就更新这里
    assert LIGHT.page == (249, 249, 246)
    assert LIGHT.card == (255, 255, 255)
    assert LIGHT.accent == (193, 113, 81)


# ---------- 两列排布 ----------


def test_column_positions_fills_shortest_column() -> None:
    heights = [100.0, 100.0, 100.0, 100.0]
    positions = column_positions(heights, top=0.0, card_width=500.0, gap=20.0)
    assert len(positions) == 4
    # 前两张各占一列，第三张回到第一列（此时第一列最矮）
    assert positions[0][0] == 0.0
    assert positions[1][0] == 520.0
    assert positions[2][0] == 0.0
    assert positions[3][0] == 520.0
    # 同一列的 y 依次下移
    assert positions[2][1] == pytest.approx(120.0)
    assert positions[3][1] == pytest.approx(120.0)


def test_column_positions_balances_uneven_heights() -> None:
    heights = [300.0, 100.0, 100.0]
    positions = column_positions(heights, top=50.0, card_width=400.0, gap=10.0)
    # 第一张很高，后两张都应该落到第二列（矮的那列）
    assert positions[0][0] == 0.0
    assert positions[1][0] == 410.0
    assert positions[2][0] == 410.0
    assert positions[1][1] == pytest.approx(50.0)
    assert positions[2][1] == pytest.approx(160.0)


def test_column_positions_handles_single_card() -> None:
    positions = column_positions([200.0], top=0.0, card_width=500.0, gap=20.0)
    assert positions == [(0.0, 0.0)]


def test_column_positions_rejects_zero_columns() -> None:
    with pytest.raises(ValueError):
        column_positions([10.0], top=0.0, card_width=100.0, gap=0.0, columns=0)


def test_total_height_is_the_tallest_column_bottom() -> None:
    heights = [100.0, 50.0]
    positions = column_positions(heights, top=10.0, card_width=100.0, gap=10.0)
    assert total_height(positions, heights) == pytest.approx(110.0)
    assert total_height([], []) == 0.0


# ---------- 自适应缩放 ----------


def test_fit_scale_prefers_largest_that_fits() -> None:
    # 内容随 scale 线性变化：scale=1 时 400，刚好塞进 500 的应当仍是 1.0
    assert fit_scale(lambda scale: 400 * scale, available=500.0) == 1.0
    # 需要缩到 0.6 才塞得下（0.65 时 520 > 500）
    assert fit_scale(lambda scale: 800 * scale, available=500.0) == pytest.approx(0.6)
    # 连下限都塞不下时返回下限（由上层裁剪），不会无限收缩
    assert fit_scale(lambda scale: 1000 * scale, available=500.0) == pytest.approx(0.55)


def test_fit_scale_respects_bounds() -> None:
    # 再大也放不下时，返回下限而不是无限收缩
    assert fit_scale(lambda scale: 10_000 * scale, available=100.0) == 0.55
    assert fit_scale(lambda scale: 1.0, available=1.0, max_scale=0.9) == 0.9


def test_fit_scale_does_not_overshoot() -> None:
    # 选出的 scale 必须使内容真的放得下（否则卡片还是会溢出画框）
    def measure(scale: float) -> float:
        return 900 * scale

    scale = fit_scale(measure, available=500.0)
    assert measure(scale) <= 500.0


# ---------- tab 条定位（render 里的纯函数，不需要 Pillow）----------


def test_storyboard_tabs_from_sections() -> None:
    from app.video.render import storyboard_tabs
    from app.video.storyboard import Scene, Storyboard

    storyboard = Storyboard(
        kind="daily",
        language="zh",
        title="测试",
        scenes=[
            Scene(index=0, kind="title", heading="标题", narration="", duration_seconds=3),
            Scene(index=1, kind="section", heading="冲突与安全", narration="", duration_seconds=3),
            Scene(index=2, kind="item", heading="条目", narration="", duration_seconds=3),
            Scene(index=3, kind="section", heading="科技发展", narration="", duration_seconds=3),
            Scene(index=4, kind="closing", heading="完", narration="", duration_seconds=3),
        ],
    )
    assert storyboard_tabs(storyboard) == ["Intro", "冲突与安全", "科技发展", "Outro"]


def test_storyboard_tabs_empty_without_sections() -> None:
    from app.video.render import storyboard_tabs
    from app.video.storyboard import Scene, Storyboard

    storyboard = Storyboard(
        kind="daily",
        language="zh",
        title="测试",
        scenes=[Scene(index=0, kind="title", heading="标题", narration="", duration_seconds=3)],
    )
    # 没有 section 就不画 tab 条，而不是画一条只有 Intro/Outro 的怪条
    assert storyboard_tabs(storyboard) == []


def test_tab_index_advances_with_sections() -> None:
    from app.video.render import tab_index_for
    from app.video.storyboard import Scene, Storyboard

    scenes = [
        Scene(index=0, kind="title", heading="标题", narration="", duration_seconds=3),
        Scene(index=1, kind="section", heading="冲突与安全", narration="", duration_seconds=3),
        Scene(index=2, kind="item", heading="条目", narration="", duration_seconds=3),
        Scene(index=3, kind="section", heading="科技发展", narration="", duration_seconds=3),
    ]
    storyboard = Storyboard(kind="daily", language="zh", title="测试", scenes=scenes)
    # title 还没有进入任何章节 -> Intro（0）
    assert tab_index_for(scenes[0], storyboard) == 0
    # section 自己与它之后的条目 -> 该章节
    assert tab_index_for(scenes[1], storyboard) == 1
    assert tab_index_for(scenes[2], storyboard) == 1
    assert tab_index_for(scenes[3], storyboard) == 2
