"""配音（TTS）：命令模板与音频格式归一化。

生产 Linux 没有 macOS `say`，靠 TTS_PROVIDER=command 接 piper。
这里钉住两件容易出错、又不容易在成片里一眼看出来的事：
1. 模板里的 {text_file} / {out_file} 确实按约定传给命令；
2. 命令写出的任意采样率都会被统一成 44.1kHz 单声道——piper medium 默认 22.05kHz，
   原样拼进音轨会整段错速（ffmpeg 不报错，但听起来像声音被拉长）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.video.render import ffmpeg_path
from app.video.tts import (
    CommandTts,
    MacSayTts,
    TtsError,
    _to_wav_44k_mono,
)

HAS_FFMPEG = ffmpeg_path() is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="需要 ffmpeg + ffprobe")


def _audio_format(path: Path) -> tuple[int, int]:
    """返回 (采样率, 声道数)。"""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    rate, channels = result.stdout.strip().split(",")
    return int(rate), int(channels)


def _audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
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
    return float(result.stdout.strip())


def _write_tone(path: Path, *, rate: int, seconds: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={rate}:cl=mono",
            "-t",
            str(seconds),
            str(path),
        ],
        check=True,
    )


# ---------- 提供方选择 ----------


def test_command_tts_available_only_with_template() -> None:
    assert CommandTts(command="piper --output_file {out_file}").available() is True
    assert CommandTts(command="   ").available() is False
    assert CommandTts(command="").available() is False


def test_mac_say_available_matches_binary() -> None:
    assert MacSayTts().available() is (shutil.which("say") is not None)


def test_command_tts_rejects_empty_template() -> None:
    with pytest.raises(TtsError, match="TTS_COMMAND 为空"):
        CommandTts(command="").synthesize("旁白", Path("/tmp/never.wav"))


def test_command_tts_reports_nonzero_exit(tmp_path: Path) -> None:
    provider = CommandTts(command="exit 3")
    with pytest.raises(TtsError, match="TTS 命令失败"):
        provider.synthesize("旁白", tmp_path / "scene.wav")


def test_command_tts_reports_missing_output(tmp_path: Path) -> None:
    # 命令成功退出但没写文件：必须报错，而不是让后续 probe 静默拿到 None
    provider = CommandTts(command="true")
    with pytest.raises(TtsError, match="没有生成"):
        provider.synthesize("旁白", tmp_path / "scene.wav")


# ---------- 格式归一化 ----------


def test_to_wav_44k_mono_requires_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.video.tts as tts_module

    monkeypatch.setattr(tts_module, "ffmpeg_path", lambda: None)
    with pytest.raises(TtsError, match="未找到 ffmpeg"):
        _to_wav_44k_mono(tmp_path / "a.wav", tmp_path / "b.wav")


@needs_ffmpeg
def test_to_wav_44k_mono_normalizes_low_sample_rate(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    dst = tmp_path / "dst.wav"
    _write_tone(src, rate=22050)
    assert _audio_format(src) == (22050, 1)

    _to_wav_44k_mono(src, dst)

    assert _audio_format(dst) == (44100, 1)


@needs_ffmpeg
def test_command_tts_passes_text_file_and_normalizes(tmp_path: Path) -> None:
    """模板按约定拿到文本文件，且 22.05kHz 输出被归一化成 44.1kHz 单声道。"""
    captured = tmp_path / "captured.txt"
    out = tmp_path / "scene_000.wav"
    # {text_file}/{out_file} 由提供方替换；这里用 ffmpeg 模拟 piper 写出 22.05kHz
    command = (
        f"cp {{text_file}} {captured} && ffmpeg -y -hide_banner -loglevel error "
        f"-f lavfi -i anullsrc=r=22050:cl=mono -t 1 {{out_file}}"
    )
    provider = CommandTts(command=command)

    seconds = provider.synthesize("第一句旁白。", out)

    assert captured.read_text(encoding="utf-8") == "第一句旁白。"
    assert seconds is not None and seconds > 0
    assert _audio_format(out) == (44100, 1)
    # 中转的 raw 文件必须清掉，别在输出目录里留垃圾
    assert list(tmp_path.glob("*.raw*")) == []


@needs_ffmpeg
def test_command_tts_cleans_raw_file_on_failure(tmp_path: Path) -> None:
    """转码失败时也要清掉中转文件。"""
    out = tmp_path / "scene_000.wav"
    # 命令生成一个不是音频的文件 -> ffmpeg 转码失败
    provider = CommandTts(command="echo not-audio > {out_file}")
    with pytest.raises(TtsError, match="转码失败"):
        provider.synthesize("旁白", out)
    assert list(tmp_path.glob("*.raw*")) == []


# ---------- 音轨与画面等长 ----------


@needs_ffmpeg
def test_concat_audio_pads_clip_shorter_than_scene(tmp_path: Path) -> None:
    """配音短于分镜时必须补静音。

    narrate 会把过短的配音抬到 min_seconds 并据此给画面计时，但音频文件本身
    还是原始长度。不补足的话音轨短于视频，混流时 -shortest 会把尾巴截掉。
    """
    from app.video.storyboard import Scene, Storyboard
    from app.video.tts import SceneAudio, concat_audio

    clip_path = tmp_path / "scene_000.wav"
    _write_tone(clip_path, rate=44100, seconds=1.0)  # 实际只有 1 秒

    board = Storyboard(
        kind="daily",
        language="zh",
        title="t",
        brief_id=1,
        scenes=[
            Scene(index=0, kind="item", heading="标题", narration="短旁白", duration_seconds=2.5)
        ],
    )
    merged = concat_audio(
        [SceneAudio(index=0, path=clip_path, seconds=2.5)], board, tmp_path / "audio.wav"
    )

    assert merged is not None
    # 音轨长度必须跟着画面走（2.5s），而不是原始片段的 1.0s
    assert _audio_duration(merged) == pytest.approx(2.5, abs=0.1)
    assert _audio_format(merged) == (44100, 1)


@needs_ffmpeg
def test_concat_audio_covers_silent_scenes(tmp_path: Path) -> None:
    """没有旁白的分镜要补静音，音轨总长仍等于画面总长。"""
    from app.video.storyboard import Scene, Storyboard
    from app.video.tts import SceneAudio, concat_audio

    clip_path = tmp_path / "scene_000.wav"
    _write_tone(clip_path, rate=44100, seconds=1.0)
    board = Storyboard(
        kind="daily",
        language="zh",
        title="t",
        brief_id=1,
        scenes=[
            Scene(index=0, kind="item", heading="a", narration="有旁白", duration_seconds=1.0),
            Scene(index=1, kind="outro", heading="b", narration="", duration_seconds=2.0),
        ],
    )
    merged = concat_audio(
        [SceneAudio(index=0, path=clip_path, seconds=1.0)], board, tmp_path / "audio.wav"
    )

    assert merged is not None
    assert _audio_duration(merged) == pytest.approx(3.0, abs=0.15)
