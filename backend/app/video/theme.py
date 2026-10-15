"""视频配色与字号：两套主题。

LIGHT 是「浅色编辑风」，取自用户提供的两份排版参考截屏：
用 PIL 直接采样得到页面底 #F9F9F6、卡片底 #FFFFFF、主色（大标题与激活 tab）#C17151。
DARK 是既有风格，保留以便回退（video_theme=dark）。

主题只放「颜色与字号」这类纯数据，画图逻辑在 layout.py —— 这样主题可以单测，
也不需要 Pillow。
"""

from __future__ import annotations

from dataclasses import dataclass, field

RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    page: RGB
    card: RGB
    card_border: RGB
    ink: RGB
    ink_muted: RGB
    accent: RGB
    tab_idle_bg: RGB
    tab_idle_ink: RGB
    footer: RGB
    # 各章节图标/标题色，让「现在看的是哪一类」有颜色直觉
    section_colors: dict[str, RGB] = field(default_factory=dict)
    # 卡片网格的逐卡配色：参考截屏里 6 张卡不是同一个颜色，而是 4 色循环，
    # 让「这是不同角度」在视觉上立刻可辨（采样自用户提供的排版参考截屏）。
    card_colors: tuple[RGB, ...] = ()
    heading_size: int = 54
    card_title_size: int = 34
    body_size: int = 30
    small_size: int = 22
    tab_size: int = 24


# 采样自参考截屏（见模块文档）
LIGHT = Theme(
    name="light",
    page=(249, 249, 246),
    card=(255, 255, 255),
    card_border=(232, 230, 222),
    ink=(58, 55, 51),
    ink_muted=(138, 133, 125),
    accent=(193, 113, 81),
    tab_idle_bg=(239, 240, 230),
    tab_idle_ink=(120, 117, 110),
    footer=(150, 145, 137),
    section_colors={
        "conflict": (193, 90, 74),
        "science": (47, 125, 140),
        "labor": (176, 122, 47),
        "other": (176, 90, 140),
        "trends": (47, 125, 140),
        "sources": (120, 117, 110),
    },
    # 逐卡配色，采样自参考截屏的 6 张卡标题（陶土 / 芥黄 / 石板蓝 / 深红）
    card_colors=((200, 120, 80), (216, 168, 88), (64, 96, 112), (160, 64, 56)),
)

DARK = Theme(
    name="dark",
    page=(11, 15, 20),
    card=(19, 24, 31),
    card_border=(45, 55, 68),
    ink=(237, 242, 247),
    ink_muted=(148, 163, 184),
    accent=(94, 234, 212),
    tab_idle_bg=(28, 34, 43),
    tab_idle_ink=(148, 163, 184),
    footer=(100, 116, 139),
    section_colors={
        "conflict": (248, 113, 113),
        "science": (56, 189, 248),
        "labor": (251, 191, 36),
        "other": (167, 139, 250),
        "trends": (129, 140, 248),
        "sources": (148, 163, 184),
    },
    card_colors=((248, 113, 113), (251, 191, 36), (96, 165, 250), (167, 139, 250)),
)

THEMES: dict[str, Theme] = {"light": LIGHT, "dark": DARK}


def get_theme(name: str | None = None) -> Theme:
    """按名字取主题；未知名字回退到浅色（新的默认）。"""
    if not name:
        return LIGHT
    return THEMES.get(name.strip().lower(), LIGHT)
