"""分镜背景：纯函数部分（配色、关键词、折行）——不依赖 Pillow。

画图本身需要 Pillow（video extra），CI 不装，所以只测这些纯逻辑。
真正容易出错的是「水印会不会出现半个句子」和「英文单词会不会被劈开」，
这两件事都能在纯函数层面钉住。
"""

from __future__ import annotations

from app.video.artwork import (
    BACKGROUND,
    KIND_ACCENT,
    MAX_HEADING_WATERMARK_CHARS,
    accent_for,
    gradient_colors,
    keywords_for,
)
from app.video.render import wrap_text
from app.video.storyboard import Scene


def _scene(**kwargs: object) -> Scene:
    base = {
        "index": 0,
        "kind": "section",
        "heading": "冲突与安全",
        "narration": "默认旁白",
        "duration_seconds": 10.0,
    }
    base.update(kwargs)
    return Scene(**base)  # type: ignore[arg-type]


def test_accent_follows_kind_and_is_deterministic() -> None:
    scene = _scene(kind="item")
    assert accent_for(scene) == accent_for(_scene(kind="item"))
    # 不同类别的基调不同
    assert accent_for(_scene(kind="item")) != accent_for(_scene(kind="sources"))
    # 同类不同文本会有微差，但不会跑出邻近范围
    other = _scene(kind="item", heading="另一条完全不同的标题")
    for channel, base_channel in zip(accent_for(other), KIND_ACCENT["item"], strict=True):
        assert abs(channel - base_channel) <= 24


def test_gradient_stays_dark() -> None:
    top, bottom = gradient_colors(KIND_ACCENT["section"])
    for channel in (*top, *bottom):
        assert 0 <= channel <= 255
    # 底部必须比顶部暗，否则层次感反了
    assert sum(bottom) < sum(top)
    assert sum(top) < sum(BACKGROUND) + 120


def test_keywords_use_short_heading_verbatim() -> None:
    scene = _scene(heading="冲突与安全")
    assert keywords_for(scene)[0] == "冲突与安全"


def test_keywords_never_emit_broken_cjk_fragments() -> None:
    """回归：中文贪婪切分会产出「南非枪击案造」这种半个句子。"""
    long_heading = "南非枪击案造成二十七人死亡与霍尔木兹海峡局势持续紧张的完整报道"
    scene = _scene(heading=long_heading, narration="正文内容", display="正文内容")
    keywords = keywords_for(scene)
    assert long_heading not in keywords  # 太长，不该整条当水印
    for word in keywords:
        # 不允许出现中文碎片（没分词器时切出来的一定是断句）
        assert not any("\u4e00" <= char <= "\u9fff" for char in word), word


def test_keywords_prefer_proper_nouns() -> None:
    scene = _scene(
        heading="Israeli Gaza Strip airstrike kills senior Hamas figure",
        narration="Israel kills senior Hamas commander in Gaza strike.",
    )
    keywords = keywords_for(scene)
    assert "gaza" in keywords
    assert "hamas" in keywords


def test_keywords_respects_limit_and_stays_deterministic() -> None:
    scene = _scene(heading="Swiss voters reject stricter neutrality rules")
    assert keywords_for(scene, limit=1) == keywords_for(scene, limit=1)[:1]
    assert len(keywords_for(scene, limit=2)) <= 2


def test_keywords_empty_for_empty_scene() -> None:
    assert keywords_for(_scene(heading="", narration="", display=None)) == []


def test_heading_longer_than_threshold_not_used_verbatim() -> None:
    heading = "x" * (MAX_HEADING_WATERMARK_CHARS + 1) + " Hormuz"
    scene = _scene(heading=heading)
    assert heading not in keywords_for(scene)


def test_wrap_text_does_not_split_latin_words() -> None:
    """回归：真实成片里出现过「commande / r in Gaza strike.」。"""
    text = "Israel kills senior Hamas commander in Gaza strike and the region braces"
    lines = wrap_text(text, width=40)
    assert len(lines) > 1
    for line in lines:
        # 每行都应是完整单词的组合（除行尾可能有标点）
        assert not line.endswith(("commande", "command")), line
    joined = " ".join(lines)
    assert "commander" in joined
    # 重新拼接后单词没有被拆散
    for word in text.split():
        assert word in joined or word.strip(".,") in joined


def test_wrap_text_still_breaks_cjk_by_character() -> None:
    lines = wrap_text("中文没有空格所以要按字折行", width=10)
    assert len(lines) >= 2
    assert all(len(line) <= 5 for line in lines)
    assert "".join(lines) == "中文没有空格所以要按字折行"
