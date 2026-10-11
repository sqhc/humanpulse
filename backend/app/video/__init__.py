"""视频简报：脚本（storyboard）→ 字幕（SRT）→ 可选渲染（ffmpeg）。"""

from app.video.srt import format_timestamp, render_srt
from app.video.storyboard import Scene, Storyboard, build_storyboard, scene_seconds
from app.video.tts import (
    SceneAudio,
    TtsError,
    apply_audio_durations,
    concat_audio,
    get_tts,
    narrate,
)

__all__ = [
    "Scene",
    "SceneAudio",
    "Storyboard",
    "TtsError",
    "apply_audio_durations",
    "build_storyboard",
    "concat_audio",
    "format_timestamp",
    "get_tts",
    "narrate",
    "render_srt",
    "scene_seconds",
]
