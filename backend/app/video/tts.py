"""旁白语音合成（TTS）：可插拔提供方。

为什么要做成接口而不是直接调某个命令：
- 本机（macOS）有 `say`，质量可用且零依赖，适合开发与本地出片；
- 生产是 Linux 容器，没有 `say`——那边通常用 piper / edge-tts / 云 TTS；
- 不同提供方的调用方式差异很大，所以除了内置的 macOS say，还提供一个**命令模板**提供方，
  让用户用 `{text_file}` / `{out_file}` 接任意 CLI，不需要改代码。

关键副作用：合成后**用真实音频时长替换脚本里的估算时长**（storyboard 的时长原本按字数估），
这样字幕与画面才对得上——估算时长只是没有音频时的兜底。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.video.render import ffmpeg_path, ffprobe_path
from app.video.storyboard import Storyboard


class TtsError(RuntimeError):
    """合成失败：命令缺失、命令返回非零、或拿不到时长。"""


class TtsProvider(Protocol):
    name: str

    def available(self) -> bool:
        """当前环境能否使用（决定要不要把失败说成"配置问题"还是"没装工具"）。"""
        ...

    def synthesize(self, text: str, out_path: Path) -> float | None:
        """把 text 合成为音频写到 out_path，返回时长（秒）；拿不到返回 None。"""
        ...


def probe_seconds(path: Path) -> float | None:
    """用 ffprobe 读音频时长；没有 ffprobe 时返回 None（不阻断合成）。"""
    ffprobe = ffprobe_path()
    if ffprobe is None:
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None


@dataclass(slots=True)
class MacSayTts:
    """macOS 内置 `say`。零依赖、离线、中文用 Tingting（zh_CN）。"""

    voice: str = "Tingting"
    rate: int = 180
    name: str = "macos-say"

    def available(self) -> bool:
        return shutil.which("say") is not None

    def synthesize(self, text: str, out_path: Path) -> float | None:
        say = shutil.which("say")
        if say is None:
            raise TtsError("未找到 macOS 的 say 命令（生产 Linux 请用 TTS_PROVIDER=command）")
        aiff = out_path.with_suffix(".aiff")
        result = subprocess.run(
            [say, "-v", self.voice, "-r", str(self.rate), "-o", str(aiff), text],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise TtsError(f"say 失败：{result.stderr.strip()[:300]}")
        # 统一转成 44.1k 单声道 wav，后面拼接与混流都省事
        ffmpeg = ffmpeg_path()
        if ffmpeg is None:
            raise TtsError("未找到 ffmpeg，无法把 say 的输出转成 wav")
        convert = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(aiff),
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )
        aiff.unlink(missing_ok=True)
        if convert.returncode != 0:
            raise TtsError(f"音频转码失败：{convert.stderr.strip()[:300]}")
        return probe_seconds(out_path)


@dataclass(slots=True)
class CommandTts:
    """外部命令模板：把 piper / edge-tts / 云 TTS 的 CLI 接进来。

    模板里可用 {text_file}（UTF-8 文本文件）与 {out_file}（目标音频路径）。
    用文件而不是命令行参数传文本：旁白可能有引号、换行，直接塞进 argv 很容易出错。
    """

    command: str
    name: str = "command"

    def available(self) -> bool:
        return bool(self.command.strip())

    def synthesize(self, text: str, out_path: Path) -> float | None:
        if not self.command.strip():
            raise TtsError("TTS_PROVIDER=command 但 TTS_COMMAND 为空；请在 .env 里给出模板")
        text_file = out_path.with_suffix(".txt")
        text_file.write_text(text, encoding="utf-8")
        rendered = self.command.replace("{text_file}", str(text_file)).replace(
            "{out_file}", str(out_path)
        )
        result = subprocess.run(rendered, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise TtsError(
                f"TTS 命令失败（exit {result.returncode}）：{result.stderr.strip()[:300]}"
            )
        if not out_path.is_file():
            raise TtsError(f"TTS 命令没有生成 {out_path}；检查模板里的 {{out_file}}")
        return probe_seconds(out_path)


def get_tts() -> TtsProvider | None:
    """按配置返回提供方；none 返回 None（表示不出配音）。"""
    settings = get_settings()
    provider = settings.tts_provider.strip().lower()
    if provider in {"none", ""}:
        return None
    if provider == "macos-say":
        return MacSayTts(voice=settings.tts_voice)
    if provider == "command":
        return CommandTts(command=settings.tts_command)
    raise TtsError(
        f"未知的 tts_provider：{settings.tts_provider!r}（可选：macos-say、command、none）"
    )


@dataclass(slots=True)
class SceneAudio:
    index: int
    path: Path
    seconds: float


def narrate(
    storyboard: Storyboard,
    out_dir: Path,
    provider: TtsProvider,
    *,
    min_seconds: float = 2.0,
) -> list[SceneAudio]:
    """为每个有旁白的分镜合成音频，返回 (序号, 文件, 时长) 列表。

    没有旁白的分镜（例如纯标题）跳过——不留静音段，画面时长仍由估算值决定。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: list[SceneAudio] = []
    for scene in storyboard.scenes:
        text = (scene.narration or scene.heading or "").strip()
        if not text:
            continue
        target = out_dir / f"scene_{scene.index:03d}.wav"
        seconds = provider.synthesize(text, target)
        if seconds is None:
            seconds = scene.duration_seconds
        clips.append(SceneAudio(index=scene.index, path=target, seconds=max(seconds, min_seconds)))
    return clips


def apply_audio_durations(storyboard: Storyboard, clips: list[SceneAudio]) -> None:
    """把真实音频时长写回分镜（原地修改）。

    这是让画面与配音对齐的关键：估算时长只用于没有音频的场景。
    """
    by_index = {clip.index: clip.seconds for clip in clips}
    for scene in storyboard.scenes:
        seconds = by_index.get(scene.index)
        if seconds is not None:
            scene.duration_seconds = round(seconds, 2)


def concat_audio(clips: list[SceneAudio], storyboard: Storyboard, out_path: Path) -> Path | None:
    """把逐镜音频拼成一条与视频等长的音轨（没有旁白的镜头补静音）。"""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None or not clips:
        return None
    work = out_path.parent / "audio_parts"
    work.mkdir(parents=True, exist_ok=True)
    by_index = {clip.index: clip for clip in clips}

    parts: list[Path] = []
    for scene in storyboard.scenes:
        clip = by_index.get(scene.index)
        if clip is not None:
            parts.append(clip.path)
            continue
        # 无旁白镜头：生成等长静音，保证音轨总长与视频一致
        silence = work / f"silence_{scene.index:03d}.wav"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                f"{scene.duration_seconds:.2f}",
                str(silence),
            ],
            capture_output=True,
        )
        parts.append(silence)

    list_file = work / "concat.txt"
    list_file.write_text(
        "".join(f"file '{path.resolve()}'" + chr(10) for path in parts), encoding="utf-8"
    )
    result = subprocess.run(
        [
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
            str(list_file.resolve()),
            "-c",
            "copy",
            str(out_path.resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TtsError(f"音轨拼接失败：{result.stderr.strip()[:300]}")
    return out_path
