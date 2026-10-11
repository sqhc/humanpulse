"""卡片版式原语：圆角卡、矢量图标、tab 条、两列流式排布。

参考截屏的版式特征：浅色暖底、白色圆角卡片、卡片内「图标 + 彩色小标题 + 正文」、
顶部一条章节 tab（当前章节高亮）。

纯布局计算（column_positions / fit_font_size）与 PIL 绘制分开：前者不需要 Pillow，
CI 可以直接断言；后者只在渲染时用。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.video.theme import Theme

RGB = tuple[int, int, int]


def column_positions(
    heights: Sequence[float],
    *,
    top: float,
    card_width: float,
    gap: float,
    columns: int = 2,
) -> list[tuple[float, float]]:
    """把一串卡片高度排成多列：每张卡放进「当前最矮」的那一列。

    参考截屏里的卡片高度是参差的（内容多的卡更高），所以用流式排布而不是等高网格。
    返回每张卡的左上角坐标，顺序与输入一致。
    """
    if columns < 1:
        raise ValueError("columns 必须 >= 1")
    usable = max(1, min(columns, len(heights)))
    column_heights = [float(top)] * usable
    positions: list[tuple[float, float]] = []
    for height in heights:
        index = min(range(usable), key=lambda position: column_heights[position])
        positions.append((index * (card_width + gap), column_heights[index]))
        column_heights[index] += float(height) + gap
    return positions


def total_height(
    positions: Sequence[tuple[float, float]],
    heights: Sequence[float],
) -> float:
    """排布后的整体底部（用于判断是否需要缩放）。"""
    if not positions:
        return 0.0
    return max(y + height for (_, y), height in zip(positions, heights, strict=True))


def fit_font_size(
    text: str,
    *,
    max_size: int,
    min_size: int,
    max_width: float,
    max_lines: int,
    measure: Callable[[str, int], tuple[float, float]],
) -> int:
    """从大到小找一个能放进 max_width x max_lines 的字号。

    measure(text, size) -> (单行宽度, 行高)。传回调而不是直接用 PIL，
    这样这个函数本身可以在没有 Pillow 的环境里测。
    """
    size = max_size
    while size > min_size:
        width, height = measure(text, size)
        if width <= max_width and height * max_lines >= height:
            return size
        size -= 2
    return min_size


def draw_rounded_card(
    draw: Any,
    box: tuple[float, float, float, float],
    *,
    theme: Theme,
    radius: int = 18,
    fill: RGB | None = None,
    border: RGB | None = None,
    border_width: int = 2,
) -> None:
    """画一张圆角卡片（默认用主题的卡片底色与描边）。"""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=fill if fill is not None else theme.card,
        outline=border if border is not None else theme.card_border,
        width=border_width,
    )


def draw_icon(
    draw: Any, *, kind: str, center: tuple[float, float], color: RGB, size: int = 30
) -> None:
    """画一个简单的矢量图标（不引入任何图片资源，延续 ADR-0014）。

    每个图标都用线条/矩形拼出来，尺寸随 size 缩放。
    """
    cx, cy = center
    half = size / 2
    width = max(2, int(size * 0.14))

    if kind == "conflict":
        # 警示三角
        draw.polygon(
            [(cx, cy - half), (cx + half, cy + half), (cx - half, cy + half)],
            outline=color,
            width=width,
        )
        return
    if kind == "science":
        # 尖括号 <>
        draw.line(
            [
                (cx - half * 0.2, cy - half * 0.7),
                (cx - half, cy),
                (cx - half * 0.2, cy + half * 0.7),
            ],
            fill=color,
            width=width,
            joint="curve",
        )
        draw.line(
            [
                (cx + half * 0.2, cy - half * 0.7),
                (cx + half, cy),
                (cx + half * 0.2, cy + half * 0.7),
            ],
            fill=color,
            width=width,
            joint="curve",
        )
        return
    if kind == "labor":
        # 2x2 方格
        cell = half * 0.75
        for dx in (-1, 1):
            for dy in (-1, 1):
                draw.rectangle(
                    [
                        cx + dx * cell - cell * 0.35,
                        cy + dy * cell - cell * 0.35,
                        cx + dx * cell + cell * 0.35,
                        cy + dy * cell + cell * 0.35,
                    ],
                    fill=color,
                )
        return
    if kind == "trends":
        # 上行折线
        draw.line(
            [
                (cx - half, cy + half * 0.4),
                (cx - half * 0.2, cy - half * 0.2),
                (cx + half * 0.2, cy + half * 0.1),
                (cx + half, cy - half * 0.7),
            ],
            fill=color,
            width=width,
            joint="curve",
        )
        return
    if kind == "sources":
        # 列表：三条线 + 圆点
        for index in range(3):
            y = cy - half * 0.6 + index * (half * 0.6)
            draw.ellipse([cx - half, y - 3, cx - half + 6, y + 3], fill=color)
            draw.line([(cx - half + 14, y), (cx + half, y)], fill=color, width=width)
        return
    # other：圆圈 + i
    draw.ellipse([cx - half, cy - half, cx + half, cy + half], outline=color, width=width)
    draw.line([(cx, cy - half * 0.35), (cx, cy + half * 0.5)], fill=color, width=width)
    draw.ellipse([cx - 2, cy - half * 0.7, cx + 2, cy - half * 0.45], fill=color)


def draw_tab_bar(
    draw: Any,
    *,
    labels: Sequence[str],
    active: int,
    theme: Theme,
    font: Any,
    width: int,
    y: float = 0.0,
    height: float = 64.0,
) -> None:
    """顶部章节 tab：整条底 + 每段文字；当前段用主色底 + 白字。"""
    draw.rectangle([0, y, width, y + height], fill=theme.tab_idle_bg)
    if not labels:
        return
    segment = width / len(labels)
    for index, label in enumerate(labels):
        x0 = index * segment
        active_tab = index == active
        if active_tab:
            draw.rectangle([x0, y, x0 + segment, y + height], fill=theme.accent)
        box = draw.textbbox((0, 0), label, font=font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        # 段太窄就干脆不画：叠在一起的文字比缺一个 tab 更难看（真的出过这种画面）
        if text_width > segment - 16:
            continue
        draw.text(
            (x0 + (segment - text_width) / 2 - box[0], y + (height - text_height) / 2 - box[1]),
            label,
            font=font,
            fill=(255, 255, 255) if active_tab else theme.tab_idle_ink,
        )


def section_icon_kind(key: str) -> str:
    """章节键 -> 图标类型（未知的用 other）。"""
    if key in {"conflict", "science", "labor", "trends", "sources"}:
        return key
    return "other"


def section_color(theme: Theme, key: str) -> RGB:
    return theme.section_colors.get(key, theme.accent)


def fit_scale(
    measure_total: Callable[[float], float],
    *,
    available: float,
    max_scale: float = 1.0,
    min_scale: float = 0.55,
    step: float = 0.05,
) -> float:
    """在 [min_scale, max_scale] 里找最大的 scale 使得内容总高不超过 available。

    卡片数量由内容决定（6 张链路卡就比 4 张高），固定字号在 720p 下会溢出——
    实测 6 张卡片时最后一张被裁掉、页脚还压在卡上。所以按比例收缩，
    到 min_scale 仍放不下才交给上层裁剪（而不是直接溢出画到框外）。
    """
    scale = max_scale
    while scale > min_scale:
        if measure_total(scale) <= available:
            return round(scale, 4)
        scale -= step
    return min_scale
