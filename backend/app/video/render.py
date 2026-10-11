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
import shutil
import subprocess
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
) -> None:
    """把单个分镜画成 PNG。"""
    from PIL import ImageDraw, ImageFont

    from app.video.artwork import build_background

    # 背景是程序化生成的（渐变 + 关键词水印），不使用任何原文配图，见 artwork.py 顶部说明
    image = build_background(scene, size=(width, height), font_path=font_path, language=language)
    draw = ImageDraw.Draw(image)
    body_size = 38 if language == "zh" else 34
    heading_size = 54 if language == "zh" else 48
    footnote_size = 26
    wrap_width = 34 if language == "zh" else 68

    fonts = {
        "heading": ImageFont.truetype(font_path, heading_size),
        "body": ImageFont.truetype(font_path, body_size),
        "footnote": ImageFont.truetype(font_path, footnote_size),
    }
    colors = {"heading": INK, "body": INK, "footnote": MUTED}
    spacing = 16

    rows = scene_lines(scene, wrap_width=wrap_width)
    measured: list[tuple[str, str, float]] = []
    total_height: float = 0.0
    for role, text in rows:
        if role == "gap":
            measured.append((role, text, 0.0))
            total_height += spacing
            continue
        box = draw.textbbox((0, 0), text or " ", font=fonts[role])
        line_height = box[3] - box[1]
        measured.append((role, text, line_height))
        total_height += line_height + spacing

    cursor = max(60.0, (height - total_height) / 2)
    for role, text, line_height in measured:
        if role == "gap":
            cursor += spacing
            continue
        box = draw.textbbox((0, 0), text, font=fonts[role])
        draw.text(
            ((width - (box[2] - box[0])) / 2 - box[0], cursor - box[1]),
            text,
            font=fonts[role],
            fill=colors[role],
        )
        cursor += line_height + spacing

    # 底部固定标注：AI 生成 + 分镜序号，避免截图被误当成原文
    tag = "AI 生成摘要 · humanpulse" if language == "zh" else "AI-generated summary · humanpulse"
    draw.text((48, height - 60), tag, font=fonts["footnote"], fill=ACCENT)
    draw.text(
        (width - 140, height - 60), f"{scene.index + 1:02d}", font=fonts["footnote"], fill=MUTED
    )
    image.save(target)


def render_video(
    storyboard: Storyboard,
    out_dir: Path,
    *,
    font: str | None = None,
    keep_scenes: bool = False,
    audio_path: Path | None = None,
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
