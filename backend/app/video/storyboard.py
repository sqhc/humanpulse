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

# 朗读速度：中文按字算，英文按字符算（英文单词平均 5 个字符，14 字符/秒约等于 170 词/分）
CHARS_PER_SECOND = {"zh": 5.5, "en": 14.0}
MIN_SCENE_SECONDS = 2.5
MAX_SCENE_SECONDS = 22.0
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 25
MAX_ITEM_SCENES = 6
SUMMARY_CHARS = 220


def scene_seconds(text: str, *, language: str = "zh") -> float:
    """按字数估时长，并夹在 [MIN, MAX] 内。空文本也留一个下限，避免 0 秒分镜。"""
    per_second = CHARS_PER_SECOND.get(language, CHARS_PER_SECOND["zh"])
    raw = len(text.strip()) / per_second
    return round(max(MIN_SCENE_SECONDS, min(MAX_SCENE_SECONDS, raw)), 1)


def _clip(text: str, limit: int = SUMMARY_CHARS) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "heading": self.heading,
            "narration": self.narration,
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
        scenes.append(
            Scene(
                index=len(scenes),
                kind=scene_kind,
                heading=heading,
                narration=narration,
                duration_seconds=scene_seconds(narration or heading, language=storyboard.language),
                **extra,
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

    if items:
        heading = "来源清单" if zh else "Sources"
        listed = "；".join(f"{item.source_name or 'unknown'}：{item.title}" for item in items[:12])
        add("sources", heading, listed)

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
    add("outro", "", notice)

    storyboard.scenes = scenes
    if not items:
        storyboard.notes.append("没有素材条目，脚本只包含综述与分组")
    if storyboard.total_seconds < 20:
        storyboard.notes.append("总时长偏短，适合做短视频或图文卡")
    return storyboard
