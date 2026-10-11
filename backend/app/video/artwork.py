"""分镜背景图：程序化生成，不使用任何第三方图片。

为什么不用原文的 og:image / 配图：
ADR-0002 定的是「只存元数据、短引用与 AI 摘要」——把出版方的图片下载下来、
合成进我们自己的视频再分发，直接违反这条政策，而且难以逐张核对授权。
所以每镜的视觉由我们自己生成：底色渐变 + 关键词水印，确定性、可复现、零版权风险。

纯函数（accent_for / keywords_for）与画图分开：CI 不装 Pillow，测试只覆盖纯函数部分。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.video.storyboard import Scene

# 深色底：与站点主题一致（见 web/src/index.css 的 surface 色）
BACKGROUND = (11, 15, 20)
INK = (237, 242, 247)
MUTED = (148, 163, 184)
ACCENT = (94, 234, 212)

# 按分镜类型给一个主色，让观众对「现在看的是哪一类内容」有直觉
KIND_ACCENT: dict[str, tuple[int, int, int]] = {
    "title": (94, 234, 212),
    "trends": (129, 140, 248),
    "section": (56, 189, 248),
    "item": (251, 146, 60),
    "sources": (148, 163, 184),
    "closing": (94, 234, 212),
    "outro": (148, 163, 184),
}

# 关键词提取要滤掉的虚词/套话（中英各一份，够用即可）
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "has",
        "are",
        "was",
        "were",
        "will",
        "would",
        "been",
        "into",
        "after",
        "before",
        "over",
        "under",
        "about",
        "says",
        "said",
        "amid",
        "than",
        "then",
        "they",
        "their",
        "there",
        "these",
        "those",
        "据",
        "称",
        "消息",
        "报道",
        "表示",
        "以及",
        "同时",
        "但是",
        "因为",
        "所以",
        "进行",
        "已经",
        "可以",
        "一个",
        "这一",
        "这些",
        "目前",
        "相关",
        "内容",
        "正文",
        "细节",
    }
)

# 只取**专有名词**（首字母大写，例如 Gaza / Hormuz / Zelenskyy）与较长的英文词。
# 中文不做分词：没有分词器时贪婪切出的 2-6 字片段往往是半个句子
# （实测出现过「南非枪击案造」这种断句碎片），所以中文只允许用**标题**做水印。
_LATIN_PROPER_RE = re.compile(r"[A-Z][A-Za-z'-]{3,}")
_LATIN_WORD_RE = re.compile(r"[a-z][a-z'-]{5,}")
# 标题短到可以整条当水印的上限（超过就该用专有名词，否则水印会糊满整屏）
MAX_HEADING_WATERMARK_CHARS = 16


def _stable_hash(value: str) -> int:
    """跨进程稳定的哈希：内置 hash() 受 PYTHONHASHSEED 影响，不能用。"""
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def accent_for(scene: Scene) -> tuple[int, int, int]:
    """分镜主色：类型决定基调，文本决定同类型内的微差（保证不同镜不完全一样）。"""
    base = KIND_ACCENT.get(scene.kind, ACCENT)
    if not (scene.heading or scene.narration):
        return base
    seed = _stable_hash(f"{scene.kind}:{scene.heading[:40]}")
    # 只在 ±24 的范围内微调，避免同一类型的分镜颜色跳得太远
    shift = (seed % 49) - 24
    return tuple(max(0, min(255, channel + shift)) for channel in base)  # type: ignore[return-value]


def keywords_for(scene: Scene, *, limit: int = 2) -> list[str]:
    """挑几个有辨识度的词做背景水印，保证**永远是完整的词**。

    规则（按优先级）：
    1. 标题短于 MAX_HEADING_WATERMARK_CHARS 时直接用标题（中文标题是完整短语）；
    2. 否则取专有名词（首字母大写）；
    3. 还不够时补较长的英文词。

    刻意不从中文正文里切词：没有分词器时切出来的是半个句子，水印会变成乱码感。
    """
    keywords: list[str] = []
    heading = (scene.heading or "").strip()
    if heading and len(heading) <= MAX_HEADING_WATERMARK_CHARS:
        keywords.append(heading)

    body = " ".join(part for part in (scene.display or scene.narration, heading) if part)
    if not body.strip():
        return keywords[:limit]

    counts: dict[str, int] = {}
    order: dict[str, int] = {}
    for rank, pattern in enumerate((_LATIN_PROPER_RE, _LATIN_WORD_RE)):
        for match in pattern.findall(body):
            word = match.strip("-").lower()
            if word in _STOPWORDS or len(word) < 4 or word in keywords:
                continue
            counts[word] = counts.get(word, 0) + (2 if rank == 0 else 1)
            order.setdefault(word, len(order))

    ranked = sorted(counts, key=lambda word: (-counts[word], order[word]))
    for word in ranked:
        if len(keywords) >= limit:
            break
        keywords.append(word)
    return keywords[:limit]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


def gradient_colors(
    accent: tuple[int, int, int],
    background: tuple[int, int, int] = BACKGROUND,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """返回 (顶部色, 底部色)：顶部略带主色，底部回到深色，形成很浅的层次。"""
    top = tuple(
        min(255, int(background[index] + (accent[index] - background[index]) * 0.16))
        for index in range(3)
    )
    bottom = tuple(max(0, int(background[index] * 0.72)) for index in range(3))
    return top, bottom  # type: ignore[return-value]


def vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Any:
    """画竖直渐变。逐行画虽然朴素，但 720 行的开销可以忽略，且没有额外依赖。"""
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[index] + (bottom[index] - top[index]) * ratio) for index in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def build_background(
    scene: Scene,
    *,
    size: tuple[int, int],
    font_path: str,
    language: str = "zh",
) -> Any:
    """生成分镜背景：渐变底 + 同心圆弧 + 关键词水印 + 左上角主色条。

    确定性：同一分镜每次渲染出的图完全一致（配色与选词都只依赖文本）。
    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = size
    accent = accent_for(scene)
    top, bottom = gradient_colors(accent)
    image = vertical_gradient(size, top, bottom).convert("RGBA")

    # 几何底纹：右下角一组同心圆弧。它是「有设计感但不抢字」的安全选择——
    # 我们不用原文配图（政策所限），纯文字卡又太素。
    motif = Image.new("RGBA", size, (0, 0, 0, 0))
    motif_draw = ImageDraw.Draw(motif)
    center = (int(width * 0.88), int(height * 0.78))
    for step, radius in enumerate(range(150, 520, 74)):
        alpha = max(6, 26 - step * 4)
        motif_draw.ellipse(
            [
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            ],
            outline=(*accent, alpha),
            width=2,
        )
    image = Image.alpha_composite(image, motif)

    # 关键词水印：只放完整词（标题或专有名词），贴在左下、避开底部页脚
    words = keywords_for(scene, limit=2)
    if words:
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        watermark_size = 96 if language == "zh" else 88
        font = ImageFont.truetype(font_path, watermark_size)
        # 放在底部压暗区之上，否则水印会被压暗层吃掉一半（看起来像被裁掉）
        base_y = height - 250
        for index, word in enumerate(words):
            # 透明度刻意很低：正文是居中的，水印只该是质感，不该和正文抢注意力
            alpha = 18 - index * 8
            if alpha <= 6:
                break
            overlay_draw.text(
                (72, base_y + index * (watermark_size * 0.62)),
                word,
                font=font,
                fill=(*accent, alpha),
            )
        image = Image.alpha_composite(image, overlay)

    # 左上角一条细主色，和站点里的强调色呼应
    bar = ImageDraw.Draw(image)
    bar.rectangle([0, 0, 10, 132], fill=(*accent, 210))

    # 底部压暗，保证页脚文字在深色上依然清晰
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    shade_draw.rectangle([0, height - 110, width, height], fill=(0, 0, 0, 90))
    image = Image.alpha_composite(image, shade)
    return image.convert("RGB")
