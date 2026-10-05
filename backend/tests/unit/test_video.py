"""视频脚本与字幕：纯函数，不依赖 ffmpeg。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.schema import BriefContent, BriefSection
from app.briefs.select import SelectedItem
from app.video.render import RenderError, find_font, scene_lines, wrap_text
from app.video.srt import format_timestamp, render_srt
from app.video.storyboard import Scene, build_storyboard, scene_seconds


def _content() -> BriefContent:
    return BriefContent(
        title_zh="今日简报",
        title_en="Today brief",
        overview_zh="综述内容。" * 20,
        overview_en="Overview text." * 20,
        sections=[
            BriefSection(
                key="conflict",
                heading_zh="冲突与安全",
                heading_en="Conflict",
                bullets_zh=["要点一", "要点二"],
                bullets_en=["Point one", "Point two"],
            )
        ],
        trends_zh=["外交 86 次，上周 4 次"],
        trends_en=["Diplomacy 86, last week 4"],
        closing_zh="明天见。",
        closing_en="See you tomorrow.",
    )


def _items(count: int = 3) -> list[SelectedItem]:
    return [
        SelectedItem(
            document_id=index,
            cluster_id=index,
            title=f"标题 {index}",
            summary_zh="摘要" * 200,  # 超过 SUMMARY_CHARS，用来验证截断
            summary_en="Summary " * 60,
            score=80,
            source_name="Al Jazeera" if index % 2 else None,
            url=f"https://example.test/{index}",
            published_at=datetime(2026, 9, 27, tzinfo=UTC),
            headline_only=False,
        )
        for index in range(1, count + 1)
    ]


def test_scene_seconds_clamps() -> None:
    assert scene_seconds("", language="zh") == 2.5
    assert scene_seconds("短", language="zh") == 2.5
    assert scene_seconds("字" * 200, language="zh") == 22.0
    assert scene_seconds("字" * 55, language="zh") == 10.0


def test_storyboard_scene_order_and_language() -> None:
    board = build_storyboard(_content(), language="zh", brief_id=7, items=_items())
    kinds = [scene.kind for scene in board.scenes]
    assert kinds[0] == "title"
    assert kinds[-1] == "outro"
    assert kinds[1] == "trends"
    assert "section" in kinds
    assert "item" in kinds
    assert "sources" in kinds
    assert "closing" in kinds
    assert board.brief_id == 7
    assert board.total_seconds > 0

    english = build_storyboard(_content(), language="en", brief_id=7, items=_items())
    assert english.language == "en"
    assert english.scenes[1].heading == "Trends"
    assert english.scenes[-1].narration.startswith("Summaries")


def test_storyboard_limits_item_scenes() -> None:
    board = build_storyboard(_content(), language="zh", items=_items(20), max_items=4)
    item_scenes = [scene for scene in board.scenes if scene.kind == "item"]
    assert len(item_scenes) == 4


def test_storyboard_without_items_notes_it() -> None:
    board = build_storyboard(_content(), language="zh")
    assert not any(scene.kind == "item" for scene in board.scenes)
    assert any("没有素材条目" in note for note in board.notes)


def test_storyboard_item_carries_source_and_url() -> None:
    board = build_storyboard(_content(), language="zh", items=_items(2))
    item = next(scene for scene in board.scenes if scene.kind == "item")
    assert item.source == "Al Jazeera"
    assert item.url == "https://example.test/1"
    assert item.document_id == 1
    assert item.narration.endswith("…")  # 摘要被截断


def test_format_timestamp() -> None:
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(3661.25) == "01:01:01,250"
    assert format_timestamp(-3) == "00:00:00,000"


def test_render_srt_is_continuous_and_numbered() -> None:
    board = build_storyboard(_content(), language="zh", items=_items(2))
    srt = render_srt(board)
    blocks = [block for block in srt.strip().split("\n\n")]
    assert len(blocks) == len(board.scenes)
    assert blocks[0].startswith("1\n00:00:00,000 --> ")

    # 时间必须首尾相接：上一块的结束 == 下一块的开始
    ends = [block.split("\n")[1].split(" --> ")[1] for block in blocks]
    starts = [block.split("\n")[1].split(" --> ")[0] for block in blocks]
    assert ends[:-1] == starts[1:]


def test_render_srt_skips_empty_and_duplicate() -> None:
    board = build_storyboard(_content(), language="zh")
    board.scenes = [
        Scene(index=0, kind="title", heading="", narration="", duration_seconds=3),
        Scene(index=1, kind="x", heading="同样", narration="同样", duration_seconds=3),
        Scene(index=2, kind="y", heading="同样", narration="同样", duration_seconds=3),
    ]
    srt = render_srt(board)
    assert srt.count("-->") == 1


def test_render_srt_empty_storyboard() -> None:
    assert render_srt(build_storyboard(BriefContent(), language="zh")) != ""


def test_wrap_text_counts_cjk_as_two_columns() -> None:
    wrapped = wrap_text("中文" * 10, width=10)
    assert len(wrapped) >= 2
    assert all(len(line) <= 5 for line in wrapped)
    assert "".join(wrapped) == "中文" * 10


def test_scene_lines_marks_roles_and_source() -> None:
    scene = Scene(
        index=0,
        kind="item",
        heading="标题",
        narration="旁白",
        duration_seconds=4,
        source="BBC World",
    )
    rows = scene_lines(scene, wrap_width=30)
    roles = [role for role, _ in rows]
    assert roles[0] == "heading"
    assert "body" in roles
    assert roles[-1] == "footnote"
    assert any(text == "来源：BBC World" for _, text in rows)


def test_find_font_rejects_missing_explicit_path() -> None:
    try:
        find_font("zh", "/definitely/not/a/font.ttf")
    except RenderError as exc:
        assert "字体不存在" in str(exc)
    else:  # pragma: no cover - 只有文件恰好存在才会走到这里
        raise AssertionError("应当抛出 RenderError")
