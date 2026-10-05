# ADR-0010：视频简报（脚本 + 字幕 + 可选渲染）

- 状态：已接受
- 日期：2026-10
- 决策者：sqhc

## 背景

Phase 3 计划里有「视频简报」。简报本身已经是结构化的双语内容（标题 / 综述 / 分组要点 / 趋势 / 来源清单），
理论上可以直接当脚本用。要考虑的是：做到哪一步、依赖什么、以及不做什么。

## 决策

1. **分三层，先做确定性的那两层**：
   - `app/video/storyboard.py`：把简报变成**分镜脚本**（纯函数）——每镜有 heading（屏幕大字）、
     narration（旁白）、时长、来源、原文链接。时长按字数估算并夹在 [2.5s, 22s]。
   - `app/video/srt.py`：由脚本生成 **SRT 字幕**（纯函数），时间轴连续无空档。
   - `app/video/render.py`：**可选**渲染 MP4。
2. **不重新调用模型**。脚本内容 100% 来自已入库的简报，因此导出脚本**零成本**、可复现；
   这也意味着脚本质量的上限就是简报质量。
3. **渲染不进 API 镜像**。需要两个外部依赖：
   - `ffmpeg`（编码）+ `Pillow`（画分镜，`uv sync --extra video`）；
   - 不把它们塞进 API/worker 镜像：几十 MB 的依赖不该进请求路径，渲染是离线/运维动作。
   缺依赖时明确报错（缺 ffmpeg 提示安装，缺 Pillow 提示 `uv sync --extra video`），而不是静默降级。
4. **用 PIL 画字，不用 ffmpeg 的 drawtext**。实测本机 ffmpeg 8.1 未编译 libfreetype，
   `drawtext` 直接报 `No such filter`；而且 drawtext 的多行排版与字体回退很难控制。
   用 PIL 可以把折行、字号层级、页脚「AI 生成摘要 · humanpulse」和分镜序号都握在自己手里。
5. **不做 TTS（本版）**。没有接入语音合成，因此产出的是**无声字幕视频** + 脚本 + SRT。
   口播稿就在脚本里，接任意 TTS 都只是把 narration 逐镜转音频再合成。
6. **接口**：`GET /briefs/{id}/storyboard`、`GET /briefs/{id}/subtitles.srt`（都支持 `language=zh|en`，
   只读、无需管理员 Key）；前端简报页提供两个下载链接。

## 实测

对真实周报（brief 3，14 个分镜）执行 `make video BRIEF_ID=3 RENDER=1`：

```
{"scenes": 14, "total_seconds": 272.3,
 "video": {"seconds": 272.36, "width": 1280, "height": 720,
           "bytes": 2864590, "font": "/System/Library/Fonts/PingFang.ttc"}}
```

抽帧检查：中文正常渲染（不是方框）、居中折行、页脚带 AI 标注与分镜号。

## 后果

- 4.5 分钟的无声视频**不能直接当成成片发布**：它需要配音或人工剪辑。这是刻意的——
  先把可控的部分（脚本、字幕、排版）做扎实，音频依赖单独引入。
- 渲染耗时约等于视频时长（14 个分镜约 20 秒），静态画面没有动效。
- 生产上要出片，机器需要 `ffmpeg` + 一个 CJK 字体（如 `fonts-noto-cjk`）；
  `find_font()` 会给出明确的缺失提示。
- 待办：TTS（narration → 音频轨）、每镜配图（目前只有深色背景 + 文字）。
