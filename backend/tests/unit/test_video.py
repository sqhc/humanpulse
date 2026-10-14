"""视频脚本与字幕：纯函数，不依赖 ffmpeg。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.briefs.schema import BriefContent, BriefSection
from app.briefs.select import SelectedItem
from app.video.render import RenderError, find_font, scene_lines, wrap_text
from app.video.srt import format_timestamp, render_srt
from app.video.storyboard import (
    CHARS_PER_SECOND,
    MIN_CHUNK_CHARS,
    SOFT_MAX_SCENE_SECONDS,
    Scene,
    build_storyboard,
    scene_seconds,
    split_long_text,
)


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
    # 只保下限、不封顶：早先写死 22s 上限，导致 597 字的段落只给 8 秒画面，观众读不完
    assert scene_seconds("字" * 200, language="zh") == round(200 / CHARS_PER_SECOND["zh"], 1)
    assert scene_seconds("字" * 55, language="zh") == round(55 / CHARS_PER_SECOND["zh"], 1)


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
    """max_items 限制的是**素材条数**；一条长摘要可以拆成多张卡。"""
    board = build_storyboard(_content(), language="zh", items=_items(20), max_items=4)
    item_scenes = [scene for scene in board.scenes if scene.kind == "item"]
    # 只统计带 document_id 的卡：续卡的 extra 是空的
    covered = {scene.document_id for scene in item_scenes if scene.document_id is not None}
    assert len(covered) == 4
    assert len(item_scenes) >= 4


def test_storyboard_without_items_notes_it() -> None:
    board = build_storyboard(_content(), language="zh")
    assert not any(scene.kind == "item" for scene in board.scenes)
    assert any("没有素材条目" in note for note in board.notes)


def test_storyboard_item_carries_source_and_url() -> None:
    """来源挂在某条素材的**最后一段**上，不跟着每一段重复。"""
    board = build_storyboard(_content(), language="zh", items=_items(2))
    first_item_scenes = [s for s in board.scenes if s.kind == "item" and s.document_id == 1]
    assert first_item_scenes
    assert first_item_scenes[-1].source == "Al Jazeera"
    assert first_item_scenes[-1].url == "https://example.test/1"
    # 中间段落不重复来源
    assert all(s.source is None for s in first_item_scenes[:-1])
    assert first_item_scenes[0].narration.endswith("…")  # 摘要被截断


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


def test_split_long_text_breaks_on_sentence_end() -> None:
    """长段旁白要按句切开，而不是让一张卡塞满几百字。"""
    text = "。".join([f"这是第{index}句话，用来测试切分。" for index in range(1, 21)])
    chunks = split_long_text(text, language="zh")
    assert len(chunks) > 1
    limit = int(SOFT_MAX_SCENE_SECONDS * CHARS_PER_SECOND["zh"])
    # 允许 MIN_CHUNK_CHARS 的溢出：合并过短碎片（例如孤立的一个「。」）比
    # 严格卡住上限更重要——否则会出现只有一两个字的卡。
    assert all(len(chunk) <= limit + MIN_CHUNK_CHARS for chunk in chunks)
    # 切分不该丢内容（空白差异除外）
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_split_long_text_short_text_untouched() -> None:
    assert split_long_text("一句很短的话。", language="zh") == ["一句很短的话。"]
    assert split_long_text("", language="zh") == []


def test_split_long_text_hard_cuts_when_no_punctuation() -> None:
    """没有句末标点的超长文本必须硬切，否则还是会挤爆一张卡。"""
    text = "字" * 900
    chunks = split_long_text(text, language="zh")
    limit = int(SOFT_MAX_SCENE_SECONDS * CHARS_PER_SECOND["zh"])
    assert len(chunks) >= 6
    assert all(len(chunk) <= limit for chunk in chunks)
    assert "".join(chunks) == text


def test_cards_empty_by_default() -> None:
    """验证 Scene.cards 默认为 None（P0 填卡片网格前，item 分镜不带 cards）。"""
    board = build_storyboard(_content(), language="zh", items=_items(2))
    item_scenes = [scene for scene in board.scenes if scene.kind == "item"]
    assert item_scenes, "应有 item 分镜"
    assert all(scene.cards is None for scene in item_scenes)


def test_deep_dive_fills_info_slots() -> None:
    """P0a：深挖分镜用确定性信息槽填卡片（事件/来源/要点/话题/涉及方/地区）。"""
    item = SelectedItem(
        document_id=1,
        cluster_id=1,
        title="测试事件",
        summary_zh="这是首句。这是第二句。",
        summary_en="First sentence. Second sentence.",
        score=90,
        source_name="测试来源",
        url="https://example.test/1",
        published_at=datetime(2026, 9, 27, tzinfo=UTC),
        headline_only=False,
        tags=["conflict", "diplomacy"],
        regions=["中东"],
        entities=[
            {"name": "实体A", "kind": "org", "salience": 0.9},
            {"name": "实体B", "kind": "person", "salience": 0.5},
            {"name": "实体C", "kind": "place", "salience": 0.2},
        ],
    )
    board = build_storyboard(_content(), language="zh", items=[item])
    deep = [s for s in board.scenes if s.kind == "deep_dive"]
    assert len(deep) == 1
    cards = deep[0].cards
    assert cards is not None and 1 <= len(cards) <= 6
    labels = [label for label, _ in cards]
    assert labels[0] == "事件"
    assert {"来源", "要点", "话题", "涉及方", "地区"} <= set(labels)
    involved = next(body for label, body in cards if label == "涉及方")
    assert "实体A" in involved and "实体B" in involved and "实体C" in involved


def test_deep_dive_omits_empty_slots() -> None:
    """P0a：空槽省略——没有来源/话题/涉及方/地区就不出现这些卡。"""
    item = SelectedItem(
        document_id=1,
        cluster_id=1,
        title="标题",
        summary_zh="一句话摘要。",
        summary_en="One sentence.",
        score=70,
        source_name=None,
        url="https://example.test/1",
        published_at=None,
        headline_only=False,
    )
    board = build_storyboard(_content(), language="zh", items=[item])
    deep = [s for s in board.scenes if s.kind == "deep_dive"]
    assert len(deep) == 1
    labels = {label for label, _ in (deep[0].cards or [])}
    assert "话题" not in labels
    assert "涉及方" not in labels
    assert "地区" not in labels
    assert "来源" not in labels


def test_long_section_becomes_multiple_scenes() -> None:
    """这是那个真实 bug 的回归测试：597 字的段落曾经只给 8 秒画面。"""
    content = BriefContent(
        title_zh="标题",
        sections=[
            BriefSection(
                key="conflict",
                heading_zh="冲突与安全",
                bullets_zh=["要点。" * 120],
            )
        ],
    )
    board = build_storyboard(content, language="zh")
    section_scenes = [scene for scene in board.scenes if scene.kind == "section"]
    assert len(section_scenes) > 1
    assert section_scenes[0].heading == "冲突与安全"
    assert section_scenes[1].heading == "冲突与安全（续）"
    # 每张卡的时长与它的字数相称，而不是被钉在 22 秒
    limit = SOFT_MAX_SCENE_SECONDS + 1.0
    assert all(scene.duration_seconds <= limit for scene in section_scenes)


def test_providerless_estimate_is_not_truncated() -> None:
    """没有配音时，估算总时长也要接近真实朗读时长（差得太多说明上限又在作祟）。"""
    content = BriefContent(
        title_zh="标题",
        overview_zh="内容。" * 200,
        sections=[],
    )
    board = build_storyboard(content, language="zh")
    chars = sum(len(scene.narration or scene.heading) for scene in board.scenes)
    expected = chars / CHARS_PER_SECOND["zh"]
    assert abs(board.total_seconds - expected) < 2.0
