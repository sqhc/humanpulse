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


def _to_wav_44k_mono(src: Path, dst: Path) -> None:
    """把任意 TTS 输出统一转成 44.1kHz 单声道 wav。

    这一步是必须的，不是可选的：拼接音轨用的是 `-c copy`（见 concat_audio），
    所有片段必须同格式。piper 的 medium 模型默认输出 22.05kHz，若原样拼进去，
    混流出来的音轨会整段错速——听感像「声音被拉长」，但 ffmpeg 不会报错。
    """
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise TtsError("未找到 ffmpeg，无法把 TTS 输出转成 44.1kHz 单声道 wav")
    convert = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-ar",
            "44100",
            "-ac",
            "1",
            str(dst),
        ],
        capture_output=True,
        text=True,
    )
    if convert.returncode != 0:
        raise TtsError(f"音频转码失败：{convert.stderr.strip()[:300]}")


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
        try:
            # 统一转成 44.1k 单声道 wav，后面拼接与混流都省事
            _to_wav_44k_mono(aiff, out_path)
        finally:
            aiff.unlink(missing_ok=True)
        return probe_seconds(out_path)


@dataclass(slots=True)
class CommandTts:
    """外部命令模板：把 piper / edge-tts / 云 TTS 的 CLI 接进来。

    模板里可用 {text_file}（UTF-8 文本文件）与 {out_file}（目标音频路径）。
    用文件而不是命令行参数传文本：旁白可能有引号、换行，直接塞进 argv 很容易出错。

    生产（Linux）没有 macOS `say`，就是靠这个接 piper：

        TTS_PROVIDER=command
        TTS_COMMAND='piper --model /models/zh_CN.onnx --output_file {out_file} < {text_file}'

    命令写出的音频**不要求**是目标格式：合成后统一转成 44.1kHz 单声道 wav
    （piper medium 默认 22.05kHz，直接拼进音轨会整段错速，见 _to_wav_44k_mono）。
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
        # 先让命令写到一个「原始」文件，再统一转码到 out_path：
        # 命令可能是 mp3/flac/任意采样率，且 ffmpeg 不能原地读写同一个文件。
        raw_path = out_path.with_name(f"{out_path.stem}.raw{out_path.suffix}")
        rendered = self.command.replace("{text_file}", str(text_file)).replace(
            "{out_file}", str(raw_path)
        )
        result = subprocess.run(rendered, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise TtsError(
                f"TTS 命令失败（exit {result.returncode}）：{result.stderr.strip()[:300]}"
            )
        if not raw_path.is_file():
            raise TtsError(f"TTS 命令没有生成 {raw_path}；检查模板里的 {{out_file}}")
        try:
            _to_wav_44k_mono(raw_path, out_path)
        finally:
            raw_path.unlink(missing_ok=True)
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
            # 配音可能短于分镜时长：narrate 会把过短的配音抬到 min_seconds，
            # 画面按抬高后的值计时，但音频文件还是原始长度。不补足的话
            # 整条音轨会短于视频，混流时被 -shortest 截掉尾巴、逐镜越差越多。
            target = round(scene.duration_seconds, 2)
            actual = probe_seconds(clip.path)
            if actual is not None and actual + 0.05 < target:
                padded = work / f"pad_{scene.index:03d}.wav"
                pad = subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        str(clip.path),
                        "-af",
                        "apad",
                        "-t",
                        f"{target:.2f}",
                        "-ar",
                        "44100",
                        "-ac",
                        "1",
                        str(padded),
                    ],
                    capture_output=True,
                )
                # 补静音失败不该让整条音轨消失：退回原始片段，至少还有声音
                parts.append(padded if pad.returncode == 0 else clip.path)
            else:
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
