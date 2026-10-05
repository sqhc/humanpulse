"""SRT 字幕：由 storyboard 的时长累加生成，纯函数。"""

from __future__ import annotations

from app.video.storyboard import Scene, Storyboard


def format_timestamp(seconds: float) -> str:
    """SRT 时间戳：HH:MM:SS,mmm。负数与小数秒都要处理。"""
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _text_for(scene: Scene) -> str:
    """屏幕上给字幕的文本：优先旁白，没有旁白就退回标题。"""
    narration = (scene.narration or "").strip()
    heading = (scene.heading or "").strip()
    if narration and heading and heading not in narration:
        return f"{heading}\n{narration}"
    return narration or heading


def render_srt(storyboard: Storyboard, *, merge_short: float = 1.2) -> str:
    """生成 SRT 文本。

    相邻分镜之间不留空隙：视频是一条时间线，字幕也必须连续，否则播放器会出现空档。
    """
    blocks: list[str] = []
    cursor = 0.0
    previous_text: str | None = None
    previous_index = 0
    for scene in storyboard.scenes:
        text = _text_for(scene)
        if not text:
            continue
        start = cursor
        duration = max(scene.duration_seconds, merge_short)
        cursor = round(cursor + duration, 3)
        if text == previous_text:
            # 连续两条完全相同的字幕没有意义，直接跳过
            continue
        previous_text = text
        previous_index += 1
        blocks.append(
            f"{previous_index}\n{format_timestamp(start)} --> {format_timestamp(cursor)}\n{text}"
        )
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"
