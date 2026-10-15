"""把 storyboard 渲染成 MP4：PIL 画分镜（PNG），ffmpeg 负责编码与拼接。

为什么不直接用 ffmpeg 的 drawtext：
- drawtext 需要 ffmpeg 编译时带 libfreetype；本地这台 Homebrew ffmpeg 就没有，
  报错是 "No such filter: 'drawtext'"，而生产镜像里根本没有 ffmpeg；
- 用 PIL 画字可以把排版（折行、标题层级、页脚来源、AI 标注）控制在自己手里，
  并且中文字体缺失时能在画之前就明确报错。

因此渲染需要两个可选依赖：ffmpeg（编码）+ Pillow（画图）。
两者都是**离线/运维动作**，不进 API 镜像；缺哪个就明确告诉用户装哪个。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.video.storyboard import Scene, Storyboard

FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

BACKGROUND = (11, 15, 20)
ACCENT = (94, 234, 212)
INK = (237, 242, 247)
MUTED = (148, 163, 184)
MAX_LINES = 12


class RenderError(RuntimeError):
    """渲染失败：ffmpeg/Pillow 缺失、字体缺失、或画/编码失败。"""


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def pillow_available() -> bool:
    try:
        import PIL  # noqa: F401  # type: ignore[import-untyped]
    except ImportError:
        return False
    return True


def find_font(language: str = "zh", explicit: str | None = None) -> str:
    """找一个能显示中文的字体；显式指定优先。"""
    if explicit:
        if not Path(explicit).is_file():
            raise RenderError(f"指定的字体不存在：{explicit}")
        return explicit
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    if language == "en":
        raise RenderError("找不到任何可用字体（英文至少需要 DejaVu 之类的矢量字体）")
    raise RenderError("找不到中文字体，渲染出来会是方框。请装 fonts-noto-cjk 或用 --font 指定")


def _wrap_tokens(text: str) -> list[str]:
    """切成不可再分的单元：CJK 一字一个，拉丁/数字整词一个。

    为什么要分词而不是逐字符：英文逐字符折行会把单词劈开——
    真实成片里出现过 commande / r in Gaza strike.，看起来像排版坏了。
    CJK 没有词间空格，所以仍然按字折行。
    """
    tokens: list[str] = []
    buffer = ""
    for char in text:
        if char.isspace():
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(" ")
            continue
        if ord(char) > 0x2E80:
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(char)
            continue
        buffer += char
    if buffer:
        tokens.append(buffer)
    return tokens


def wrap_text(text: str, *, width: int) -> list[str]:
    """按显示宽度折行：CJK 算 2 列、其它算 1 列；不切开拉丁单词。"""
    lines: list[str] = []
    current = ""
    used = 0
    for token in _wrap_tokens(" ".join(text.split())):
        if token == " ":
            if current:
                current += " "
                used += 1
            continue
        size = sum(2 if ord(char) > 0x2E80 else 1 for char in token)
        if used + size > width and current:
            lines.append(current.rstrip())
            current = ""
            used = 0
        current += token
        used += size
    if current.strip():
        lines.append(current.rstrip())
    return lines


def scene_lines(scene: Scene, *, wrap_width: int) -> list[tuple[str, str]]:
    """返回 [(角色, 文本)]，角色用于决定字号/颜色：heading 大字、body 正文、footnote 小字。

    正文优先取 display（只看不念的内容，例如来源清单），没有再退回 narration。
    """
    rows: list[tuple[str, str]] = []
    if scene.heading:
        rows.extend(("heading", line) for line in wrap_text(scene.heading, width=wrap_width))
    body = scene.display or scene.narration
    if body and body != scene.heading:
        if rows:
            rows.append(("gap", ""))
        rows.extend(("body", line) for line in wrap_text(body, width=wrap_width))
    if scene.source:
        rows.append(("gap", ""))
        rows.append(("footnote", f"来源：{scene.source}"))
    return rows[:MAX_LINES]


def render_scene_png(
    scene: Scene,
    target: Path,
    *,
    font_path: str,
    width: int,
    height: int,
    language: str,
    theme_name: str | None = None,
    tab_labels: Sequence[str] = (),
    active_tab: int = 0,
) -> None:
    """把单个分镜画成 PNG。

    版式对照用户提供的排版参考截屏：暖色浅底、顶部章节 tab 条（当前章节高亮）、
    主色大标题、白色圆角卡片承载正文。卡片内容放在 scene.cards 时渲染成两列网格。
    """
    from PIL import Image, ImageDraw, ImageFont

    from app.video.layout import (
        card_color,
        card_icon_kind,
        column_positions,
        draw_icon,
        draw_rounded_card,
        draw_tab_bar,
        fit_scale,
        total_height,
    )
    from app.video.theme import get_theme

    theme = get_theme(theme_name)
    image = Image.new("RGB", (width, height), theme.page)
    draw = ImageDraw.Draw(image)

    heading_size = theme.heading_size if language == "zh" else int(theme.heading_size * 0.88)
    body_size = theme.body_size if language == "zh" else int(theme.body_size * 0.92)
    small_size = theme.small_size
    fonts = {
        "heading": ImageFont.truetype(font_path, heading_size),
        "body": ImageFont.truetype(font_path, body_size),
        "small": ImageFont.truetype(font_path, small_size),
        "card": ImageFont.truetype(font_path, theme.card_title_size),
        "tab": ImageFont.truetype(font_path, theme.tab_size),
        "icon": ImageFont.truetype(font_path, small_size),
    }

    top = 24.0
    if tab_labels:
        draw_tab_bar(
            draw,
            labels=list(tab_labels),
            active=active_tab,
            theme=theme,
            font=fonts["tab"],
            width=width,
        )
        top = 64.0 + 34.0

    # 标题：主色大字（截屏里的大标题就是这个颜色）
    title = scene.heading.strip()
    if title:
        wrap_width = 30 if language == "zh" else 58
        lines = wrap_text(title, width=wrap_width)
        cursor = top
        for line in lines:
            box = draw.textbbox((0, 0), line, font=fonts["heading"])
            draw.text(
                ((width - (box[2] - box[0])) / 2 - box[0], cursor - box[1]),
                line,
                font=fonts["heading"],
                fill=theme.accent,
            )
            cursor += (box[3] - box[1]) + 14
        top = cursor + 18

    card_left = 64.0
    card_right = width - 64.0
    card_width = card_right - card_left
    bottom_limit = height - 74.0

    if scene.cards:
        # 卡片网格 + 自适应缩放：默认 3 列（对照排版参考截屏的 3×2 版式）。
        # 卡片少时列多会挤，所以按数量挑列数：<=2 单列、3~4 两列、5+ 三列。
        from app.video.layout import CARD_GRID_COLUMNS

        count = len(scene.cards)
        columns = 1 if count <= 2 else (2 if count <= 4 else CARD_GRID_COLUMNS)
        gap = 22.0
        column_width = (card_width - gap * (columns - 1)) / columns
        available = bottom_limit - top
        base_pad_x, base_pad_y = 26.0, 20.0

        def metrics(scale: float) -> tuple[float, float, int, int, int, int, int]:
            pad_x = base_pad_x * scale
            pad_y = base_pad_y * scale
            title_size = max(16, int(theme.card_title_size * scale))
            text_size = max(15, int(body_size * scale))
            line_gap = max(4, int(10 * scale))
            icon_gap = max(24, int(40 * scale))
            # 正文不缩进（只有小标题那行给图标让位），所以折行宽度按整卡可用宽算。
            # 之前把 icon_gap 也减掉，导致正文被误判成 2 行、卡片高度虚高、
            # 自适应把字号缩到 0.6 左右，画面右下角留出一大片空白。
            usable = max(120.0, column_width - 2 * pad_x)
            wrap_width = max(8, int(2 * usable / text_size))
            return pad_x, pad_y, title_size, text_size, line_gap, icon_gap, wrap_width

        def build(scale: float) -> tuple[list[tuple[str, list[str], float]], float]:
            _pad_x, _pad_y, title_size, text_size, line_gap, _icon_gap, wrap_width = metrics(scale)
            entries: list[tuple[str, list[str], float]] = []
            heights: list[float] = []
            for label, body in scene.cards or []:
                body_lines = wrap_text(body, width=wrap_width)
                height = 2 * base_pad_y * scale + (title_size + 12 * scale if label else 0.0)
                height += len(body_lines) * (text_size + line_gap)
                entries.append((label, body_lines, height))
                heights.append(height)
            positions = column_positions(
                heights, top=top, card_width=column_width, gap=gap, columns=columns
            )
            return entries, total_height(positions, heights)

        scale = fit_scale(lambda value: build(value)[1], available=available)
        entries, _ = build(scale)
        pad_x, pad_y, title_size, text_size, line_gap, icon_gap, _wrap = metrics(scale)
        heights = [entry[2] for entry in entries]
        positions = column_positions(
            heights, top=top, card_width=column_width, gap=gap, columns=columns
        )
        # 内容比可用区域矮时把整块网格垂直居中，否则卡片全贴顶、下半屏空得很难看
        grid_bottom = total_height(positions, heights)
        offset_y_center = max(0.0, (bottom_limit - grid_bottom) / 2)
        if offset_y_center > 0:
            positions = [(x, y + offset_y_center) for x, y in positions]
        small_card_font = ImageFont.truetype(font_path, title_size)
        small_body_font = ImageFont.truetype(font_path, text_size)

        # 注意：这里不能用 height 当循环变量，它会覆盖函数参数（画框高度），
        # 导致循环之后的页脚被画到错误位置。mypy 抓到了这个遮蔽。
        for card_index, ((label, body_lines, card_height), (offset_x, offset_y)) in enumerate(
            zip(entries, positions, strict=True)
        ):
            box = (
                card_left + offset_x,
                offset_y,
                card_left + offset_x + column_width,
                offset_y + card_height,
            )
            draw_rounded_card(draw, box, theme=theme, radius=18)
            inner_x = box[0] + pad_x
            cursor_y = box[1] + pad_y
            if label:
                # 逐卡配色（截屏里 6 张卡是 4 色轮转），图标跟着小标题语义走
                color = card_color(theme, card_index)
                draw_icon(
                    draw,
                    kind=card_icon_kind(label),
                    center=(inner_x + icon_gap * 0.35, cursor_y + title_size / 2),
                    color=color,
                    size=max(18, int(26 * scale)),
                )
                draw.text((inner_x + icon_gap, cursor_y), label, font=small_card_font, fill=color)
                cursor_y += title_size + 12 * scale
            for line in body_lines:
                if cursor_y + text_size > box[3] - pad_y * 0.5:
                    break
                draw.text((inner_x, cursor_y), line, font=small_body_font, fill=theme.ink)
                cursor_y += text_size + line_gap
    else:
        body = scene.display or scene.narration
        rows = wrap_text(body, width=34 if language == "zh" else 64) if body else []
        source_line = f"来源：{scene.source}" if scene.source else ""
        inner_wrap = 32 if language == "zh" else 60
        if source_line:
            rows = [*rows, "", *wrap_text(source_line, width=inner_wrap)]
        card_height = min(
            bottom_limit - top,
            max(180.0, 56.0 + len([r for r in rows if r]) * (body_size + 12)),
        )
        # 内容短时把卡片在可用区域里居中，否则整块贴顶、下半屏空得很难看
        card_top = top + max(0.0, (bottom_limit - top - card_height) / 2)
        box = (card_left, card_top, card_right, card_top + card_height)
        draw_rounded_card(draw, box, theme=theme, radius=20)
        cursor_y = box[1] + 34
        for line in rows:
            if not line:
                cursor_y += 10
                continue
            if cursor_y + body_size > box[3] - 20:
                break
            draw.text((box[0] + 34, cursor_y), line, font=fonts["body"], fill=theme.ink)
            cursor_y += body_size + 12

    tag = "AI 生成摘要 · humanpulse" if language == "zh" else "AI-generated summary · humanpulse"
    draw.text((64, height - 54), tag, font=fonts["small"], fill=theme.footer)
    draw.text(
        (width - 110, height - 54),
        f"{scene.index + 1:02d}",
        font=fonts["small"],
        fill=theme.footer,
    )
    image.save(target)


MAX_TABS = 7  # 含 Intro 与 Outro


def _base_section_name(heading: str) -> str:
    """去掉「（续）」这类续页后缀，让同一章节的多个分镜合并成一个 tab。"""
    name = heading.strip()
    while True:
        stripped = re.sub(r"[（(]\s*(续|续页|cont\.?|continued)\s*[)）]\s*$", "", name).strip()
        if stripped == name or not stripped:
            return name
        name = stripped


def storyboard_tabs(storyboard: Storyboard) -> list[str]:
    """从分镜里推出顶部 tab 的章节名：Intro + 各 section 标题 + Outro。

    两处容易踩的坑（都真的踩过）：
    1. 长章节会被切成「冲突与安全」与「冲突与安全（续）」多个 section 分镜，
       直接收集会把同一个章节算成好几个 tab —— 必须按去掉续页后缀的名字去重；
    2. tab 数量必须设上限，否则十来个 tab 挤在 1280 宽里文字会叠成一团。
    """
    sections: list[str] = []
    for scene in storyboard.scenes:
        if scene.kind != "section":
            continue
        name = _base_section_name(scene.heading)
        if name and name not in sections:
            sections.append(name)
    if not sections:
        return []
    if len(sections) > MAX_TABS - 2:
        # 章节太多就均匀取样，保证首尾都在
        step = len(sections) / (MAX_TABS - 2)
        sections = [
            sections[min(len(sections) - 1, int(index * step))] for index in range(MAX_TABS - 2)
        ]
    return ["Intro", *sections, "Outro"]


def tab_index_for(scene: Scene, storyboard: Storyboard) -> int:
    """当前分镜应高亮第几个 tab：它之前（含）最后一个 section 的位置。"""
    tabs = storyboard_tabs(storyboard)
    if not tabs:
        return 0
    sections = [name.strip() for name in tabs[1:-1]]
    active = 0
    for candidate in storyboard.scenes:
        if candidate.index > scene.index:
            break
        if candidate.kind != "section":
            continue
        name = _base_section_name(candidate.heading)
        if name in sections:
            active = sections.index(name) + 1
    return active


def render_video(
    storyboard: Storyboard,
    out_dir: Path,
    *,
    font: str | None = None,
    keep_scenes: bool = False,
    audio_path: Path | None = None,
    theme_name: str | None = None,
) -> dict[str, Any]:
    """渲染 MP4；返回 path/seconds/width/height/bytes/font/scenes/audio。"""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise RenderError("未找到 ffmpeg，无法渲染视频（脚本与字幕仍可正常导出）")
    if not pillow_available():
        raise RenderError("未安装 Pillow，无法画分镜：uv sync --extra video")
    if not storyboard.scenes:
        raise RenderError("storyboard 没有分镜")

    font_path = find_font(storyboard.language, font)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = out_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)

    width, height, fps = storyboard.width, storyboard.height, storyboard.fps
    tabs = storyboard_tabs(storyboard)
    scene_files: list[Path] = []
    for scene in storyboard.scenes:
        image = scenes_dir / f"scene_{scene.index:03d}.png"
        render_scene_png(
            scene,
            image,
            font_path=font_path,
            width=width,
            height=height,
            language=storyboard.language,
            theme_name=theme_name,
            tab_labels=tabs,
            active_tab=tab_index_for(scene, storyboard),
        )
        target = scenes_dir / f"scene_{scene.index:03d}.mp4"
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            f"{scene.duration_seconds:.2f}",
            "-r",
            str(fps),
            "-vf",
            f"scale={width}:{height}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RenderError(f"第 {scene.index} 个分镜编码失败：{result.stderr.strip()[:400]}")
        scene_files.append(target)

    concat_file = scenes_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{path.name}'" + chr(10) for path in scene_files), encoding="utf-8"
    )
    final = out_dir / f"brief-{storyboard.brief_id or 'x'}-{storyboard.language}.mp4"
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file.resolve()),
        "-c",
        "copy",
        str(final.resolve()),
    ]
    result = subprocess.run(command, capture_output=True, text=True, cwd=scenes_dir)
    if result.returncode != 0:
        raise RenderError(f"拼接失败：{result.stderr.strip()[:400]}")

    # 有音轨就混流进来：-shortest 让视频/音频取较短者，避免尾部出现黑屏或静音拖尾
    audio_note: str | None = None
    if audio_path is not None and audio_path.is_file():
        with_audio = out_dir / f"{final.stem}-audio.mp4"
        mux = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(final.resolve()),
                "-i",
                str(audio_path.resolve()),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                str(with_audio.resolve()),
            ],
            capture_output=True,
            text=True,
        )
        if mux.returncode != 0:
            # 混流失败不该丢掉已经渲染好的无声视频
            audio_note = f"混流失败，已保留无声视频：{mux.stderr.strip()[:200]}"
        else:
            final.unlink(missing_ok=True)
            with_audio.rename(final)

    if not keep_scenes:
        shutil.rmtree(scenes_dir, ignore_errors=True)

    info = probe_video(final)
    return {
        "path": str(final),
        "seconds": info.get("seconds"),
        "width": info.get("width"),
        "height": info.get("height"),
        "bytes": final.stat().st_size,
        "font": font_path,
        "scenes": len(scene_files),
        "has_audio": audio_path is not None and audio_path.is_file() and audio_note is None,
        "audio_note": audio_note,
    }


def probe_video(path: Path) -> dict[str, Any]:
    """用 ffprobe 读回时长/分辨率，确认真的生成了可播放的文件。"""
    ffprobe = ffprobe_path()
    if ffprobe is None:
        return {}
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    streams = payload.get("streams") or [{}]
    duration = (payload.get("format") or {}).get("duration")
    return {
        "width": streams[0].get("width"),
        "height": streams[0].get("height"),
        "seconds": round(float(duration), 2) if duration else None,
    }
