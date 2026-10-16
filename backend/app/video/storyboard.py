"""视频脚本（storyboard）：把简报变成可渲染的分镜。纯函数，不调用模型。

为什么先做脚本而不是直接出片：
- 脚本是确定性的、可单测的，媒体渲染（ffmpeg）是环境相关的；
- 脚本有独立价值：可以直接当口播稿、字幕、或人工剪辑的提示单。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.briefs.schema import BriefContent
from app.briefs.select import SelectedItem

# 朗读速度：中文按字算，英文按字符算。
#
# 中文实测校准：macOS say -v Tingting -r 180 读 28 个分镜，2834 字 / 585 秒 = 4.84 字/秒。
# 英文实测校准（2026-10-13）：macOS say -v Samantha/-v Daniel -r 180 读 749 字符样文，
# 测得 19.3~19.6 字符/秒，取 19.0 兜底（略保守，避免重蹈中文「偏乐观」的覆辙）。
# 历史教训：先后写死过 5.5 与 6.2，都偏乐观——没有配音时估算总长比真实朗读短 20-30%，
# 于是每张卡停留时间不够读。不同语音/语速节奏不同，这个常数只是**兜底估算**；
# 一旦启用配音（--voice），会用真实音频时长覆盖它（见 tts.apply_audio_durations）。
CHARS_PER_SECOND = {"zh": 4.8, "en": 19.0}
MIN_SCENE_SECONDS = 2.5
# 单镜时长**不设硬上限**：
# 曾经写死 22 秒，结果一镜 597 字的内容画面只给 8 秒——没有配音时观众根本读不完。
# 现在只在预测时长超过 soft 上限时**拆成多个分镜**（见 split_long_text），而不是压缩。
SOFT_MAX_SCENE_SECONDS = 24.0
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 25
MAX_ITEM_SCENES = 6
SUMMARY_CHARS = 220


def scene_seconds(text: str, *, language: str = "zh") -> float:
    """按字数估时长；只保证下限，不封顶（封顶会让长内容读不完，见 SOFT_MAX_SCENE_SECONDS）。"""
    per_second = CHARS_PER_SECOND.get(language, CHARS_PER_SECOND["zh"])
    raw = len(text.strip()) / per_second
    return round(max(MIN_SCENE_SECONDS, raw), 1)


def split_long_text(text: str, *, language: str = "zh") -> list[str]:
    """把过长的旁白按句子切成若干段，使每段的预测时长不超过 soft 上限。

    按句末标点切分（中英文都覆盖），再贪心合并短句；宁可多切一段，也不要让一屏塞满文字。
    """
    per_second = CHARS_PER_SECOND.get(language, CHARS_PER_SECOND["zh"])
    limit = int(SOFT_MAX_SCENE_SECONDS * per_second)
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return [cleaned] if cleaned else []

    sentences: list[str] = []
    current = ""
    for char in cleaned:
        current += char
        if char in "。！？!?；;":
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    chunks: list[str] = []
    buffer = ""
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) > limit:
            chunks.append(buffer)
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        chunks.append(buffer)

    # 单句本身超长（没有标点的长句）时硬切，保证不会出现一镜几百字
    result: list[str] = []
    for chunk in chunks:
        while len(chunk) > limit:
            result.append(chunk[:limit])
            chunk = chunk[limit:]
        if chunk:
            result.append(chunk)

    return merge_tiny_chunks(result)


# 短于这个长度的碎片没有独立成镜的价值（曾经出现整整一张卡只写着一个「。」）
MIN_CHUNK_CHARS = 8


def merge_tiny_chunks(chunks: list[str]) -> list[str]:
    """把过短的碎片并进相邻段：孤立的「。」单独成镜既浪费一次转场，念出来也没有意义。"""
    merged: list[str] = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        if merged and len(stripped) < MIN_CHUNK_CHARS:
            merged[-1] = f"{merged[-1]} {stripped}".strip()
            continue
        merged.append(stripped)

    # 首段过短且后面还有内容时并到后面去，避免开场只有一个标点
    if len(merged) > 1 and len(merged[0]) < MIN_CHUNK_CHARS:
        merged[1] = f"{merged[0]} {merged[1]}".strip()
        merged.pop(0)
    return merged


def _clip(text: str, limit: int = SUMMARY_CHARS) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _first_sentence(text: str) -> str:
    """取首句（按句末标点切）；没有句末标点就截断前 80 字。"""
    cleaned = " ".join((text or "").split())
    for index, char in enumerate(cleaned):
        if char in "。！？!?；;":
            return cleaned[: index + 1]
    return _clip(cleaned, 80)


def _deep_dive_cards(item: SelectedItem, *, zh: bool) -> list[tuple[str, str]]:
    """P0a：深挖卡片——用确定性信息槽填充（空槽省略，最多 6 张）。

    这里只做占位：未来由「深度调查 agent」产出 6 个语义 facet
    （官方回应/研究/技术手法/媒体披露/监管合作/第三方观点）替换这些信息槽。
    """
    cards: list[tuple[str, str]] = []
    if item.title:
        cards.append(("事件", item.title))

    source_time = item.source_name or ""
    if item.published_at is not None:
        stamp = item.published_at.strftime("%Y-%m-%d")
        source_time = f"{source_time} · {stamp}" if source_time else stamp
    if source_time:
        cards.append(("来源", source_time))

    first = _first_sentence(item.summary_zh if zh else item.summary_en)
    if first:
        cards.append(("要点", first))

    if item.tags:
        cards.append(("话题", "、".join(item.tags[:6])))

    if item.entities:
        ranked = sorted(
            item.entities,
            key=lambda entry: float((entry or {}).get("salience", 0) or 0),
            reverse=True,
        )
        names = [str((entry or {}).get("name", "")).strip() for entry in ranked]
        names = [name for name in names if name]
        if names:
            cards.append(("涉及方", "、".join(names[:3])))

    if item.regions:
        cards.append(("地区", "、".join(item.regions[:6])))

    return cards[:6]


@dataclass(slots=True)
class Scene:
    """一个分镜：屏幕上显示什么、旁白念什么、来自哪里。"""

    index: int
    kind: str
    heading: str
    narration: str
    duration_seconds: float
    source: str | None = None
    url: str | None = None
    document_id: int | None = None
    # 屏幕上显示的正文；为空则用 narration。
    # 之所以要分开：来源清单这种内容适合「看」不适合「念」——
    # 逐个念出「来源：英文标题」既难听，中文语音读英文还会明显加速（实测 8-12 字/秒）。
    display: str | None = None
    # 卡片版式（参考截屏）：[(小标题, 正文), ...]；非空时渲染成卡片网格而不是单栏正文
    cards: list[tuple[str, str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "heading": self.heading,
            "narration": self.narration,
            "display": self.display,
            "cards": self.cards,
            "duration_seconds": self.duration_seconds,
            "source": self.source,
            "url": self.url,
            "document_id": self.document_id,
        }


@dataclass(slots=True)
class Storyboard:
    kind: str
    language: str
    title: str
    scenes: list[Scene] = field(default_factory=list)
    brief_id: int | None = None
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    fps: int = DEFAULT_FPS
    notes: list[str] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return round(sum(scene.duration_seconds for scene in self.scenes), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "kind": self.kind,
            "language": self.language,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_seconds": self.total_seconds,
            "scene_count": len(self.scenes),
            "notes": list(self.notes),
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


def build_storyboard(
    content: BriefContent,
    *,
    language: str = "zh",
    brief_id: int | None = None,
    kind: str = "daily",
    items: list[SelectedItem] | None = None,
    max_items: int = MAX_ITEM_SCENES,
) -> Storyboard:
    """把简报拼成脚本。所有文案都来自已入库的简报，不重新调用模型。"""
    zh = language != "en"
    title = (content.title_zh if zh else content.title_en) or (
        "humanpulse 简报" if zh else "humanpulse brief"
    )
    overview = content.overview_zh if zh else content.overview_en
    closing = content.closing_zh if zh else content.closing_en
    trends = content.trends_zh if zh else content.trends_en

    storyboard = Storyboard(
        kind=kind, language="zh" if zh else "en", title=title, brief_id=brief_id
    )
    scenes: list[Scene] = []

    def add(scene_kind: str, heading: str, narration: str, **extra: Any) -> None:
        """加一个分镜；旁白过长时自动拆成多张卡（而不是压缩成一张读不完的卡）。

        来源/链接等信息只挂在最后一段上：连着几张卡重复来源没有意义。
        """
        # 有 display 时，语音读 narration、屏幕显示 display，拆段只看 narration 的长度
        spoken = narration or heading
        chunks = split_long_text(spoken, language=storyboard.language) or [""]
        display_chunks = (
            split_long_text(str(extra.get("display") or ""), language=storyboard.language)
            if extra.get("display")
            else []
        )
        for position, chunk in enumerate(chunks):
            is_first = position == 0
            is_last = position == len(chunks) - 1
            if is_first or not heading:
                scene_heading = heading
            else:
                scene_heading = f"{heading}（续）" if zh else f"{heading} (cont.)"
            scenes.append(
                Scene(
                    index=len(scenes),
                    kind=scene_kind,
                    heading=scene_heading,
                    narration=chunk,
                    duration_seconds=scene_seconds(
                        chunk or scene_heading, language=storyboard.language
                    ),
                    # display 只在最后一段挂上（前面几段显示自己的 narration）
                    display=(" ".join(display_chunks) if display_chunks else None)
                    if is_last
                    else None,
                    **{k: v for k, v in extra.items() if k != "display"} if is_last else {},
                )
            )

    add("title", title, overview or title)

    if trends:
        heading = "本周趋势" if zh else "Trends"
        add("trends", heading, " ".join(f"{index}. {text}" for index, text in enumerate(trends, 1)))

    for section in content.sections:
        heading = section.heading_zh if zh else section.heading_en
        bullets = section.bullets_zh if zh else section.bullets_en
        if not bullets:
            continue
        add("section", heading, " ".join(bullets))

    for item in (items or [])[:max_items]:
        summary = item.summary_zh if zh else item.summary_en
        add(
            "item",
            item.title,
            _clip(summary) or item.title,
            source=item.source_name,
            url=item.url,
            document_id=item.document_id,
        )

    # 深挖分镜。优先用简报里**模型产出的分面**（存库字段，视频链路零模型调用）；
    # 没有分面时退回评分最高那条的确定性信息槽（空槽省略，不调模型）。
    dive = content.deep_dive
    dive_cards: list[tuple[str, str]] = (
        [facet.text_for(storyboard.language) for facet in dive.usable_facets()]
        if dive is not None
        else []
    )
    dive_cards = [(label, body) for label, body in dive_cards if body.strip()]
    dive_heading = (dive.title_for(storyboard.language) if dive is not None else "") or (
        "本期深挖" if zh else "Deep dive"
    )
    if dive_cards:
        narration = _clip("；".join(body for _, body in dive_cards)) or dive_heading
        card_text = "".join(label + body for label, body in dive_cards)
        scenes.append(
            Scene(
                index=len(scenes),
                kind="deep_dive",
                heading=dive_heading,
                narration=narration,
                duration_seconds=max(
                    scene_seconds(narration, language=storyboard.language),
                    scene_seconds(card_text, language=storyboard.language),
                ),
                cards=dive_cards,
            )
        )
    elif items:
        top = max(items, key=lambda it: it.score)
        cards = _deep_dive_cards(top, zh=zh)
        if cards:
            narration = _clip(top.summary_zh if zh else top.summary_en) or top.title
            card_text = "".join(label + body for label, body in cards)
            scenes.append(
                Scene(
                    index=len(scenes),
                    kind="deep_dive",
                    heading="本期深挖" if zh else "Deep dive",
                    narration=narration,
                    duration_seconds=max(
                        scene_seconds(narration, language=storyboard.language),
                        scene_seconds(card_text, language=storyboard.language),
                    ),
                    cards=cards,
                    source=top.source_name,
                    url=top.url,
                    document_id=top.document_id,
                )
            )

    if items:
        heading = "来源清单" if zh else "Sources"
        # 屏幕上列全量（供阅读/核对），语音只报「多少条、来自哪些源」——
        # 逐条念「来源：英文标题」既难听，中文语音读英文还会飙到 8-12 字/秒。
        listed = "；".join(f"{item.source_name or 'unknown'}：{item.title}" for item in items[:12])
        names = list(dict.fromkeys(item.source_name for item in items if item.source_name))
        spoken = (
            f"本期素材共 {len(items)} 条，来自 {len(names)} 个来源：{'、'.join(names[:8])}。"
            if zh
            else (
                f"This issue draws on {len(items)} items from {len(names)} sources: "
                f"{', '.join(names[:8])}."
            )
        )
        add("sources", heading, spoken, display=listed)

    if closing:
        add("closing", "小结" if zh else "Wrap-up", closing)

    notice = (
        "以上摘要与评分由大模型生成并标注，完整内容与原文链接见 humanpulse 网站。"
        if zh
        else (
            "Summaries and scores are AI-generated and labelled; "
            "full text and sources are on humanpulse."
        )
    )
    # 推演（projection）未通过校准评估门时，必须在画面与旁白里显式标注：
    # 概率来自模型输出、未经可靠性验证，不得当作已校准的预测发布。
    # 只在简报确实带推演内容时才加这句，避免无推演的期数也出现「本推演」字样。
    projection = content.projection
    if projection is not None and projection.chains:
        uncalibrated = (
            "本推演尚未通过校准评估：概率来自模型输出，未经可靠性验证。"
            if zh
            else (
                "This projection has not passed calibration assessment: "
                "the probabilities come from model output and have not been reliability-validated."
            )
        )
        notice = f"{notice}{uncalibrated}"
    add("outro", "", notice)

    storyboard.scenes = scenes
    if not items:
        storyboard.notes.append("没有素材条目，脚本只包含综述与分组")
    if storyboard.total_seconds < 20:
        storyboard.notes.append("总时长偏短，适合做短视频或图文卡")
    return storyboard
