"""运维 CLI：python -m app.cli <command>

- seed   ：把 infra/seed/sources.yaml 导入 sources 表
- demo   ：用合成数据跑通"采集 → 处理 → 聚类"，用于 CI 冒烟（不联网、不花钱）
- migrate：执行 alembic upgrade head
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import uuid
from typing import Any

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO_SOURCE_NAME = "demo (synthetic)"


async def _reembed() -> dict[str, Any]:
    """用当前 EMBEDDING_PROVIDER 重新嵌入所有已富化文档并重建聚类。

    用途：
      1) 从 hash 向量切到 local 语义向量后，需要重算向量与聚类；
      2) 调整 VECTOR_DUP_THRESHOLD 后想看看聚类会变成什么样（不改阈值也能先观察）。
    代价：会清空 embeddings / clusters / cluster_members 重建，可重复执行且幂等。
    """
    from sqlalchemy import delete, func, select

    from app.db import session_scope
    from app.embedding import get_embedder
    from app.models.analysis import Analysis, Cluster, ClusterMember, Embedding
    from app.models.document import Document
    from app.pipeline.dedup import attach_cluster, embedding_text

    embedder = get_embedder()
    stats: dict[str, Any] = {
        "embedder": embedder.name,
        "embedded": 0,
        "clusters": 0,
        "multi_doc_clusters": 0,
        "largest_cluster": 0,
    }

    async with session_scope() as session:
        await session.execute(delete(Embedding))
        await session.execute(delete(ClusterMember))
        await session.execute(delete(Cluster))
        await session.flush()

        rows = (
            await session.execute(
                select(Analysis, Document)
                .join(Document, Document.id == Analysis.document_id)
                .where(Document.status == "enriched")
                .order_by(
                    func.coalesce(Document.published_at, Document.fetched_at).asc(),
                    Document.id.asc(),
                )
            )
        ).all()

        for analysis, document in rows:
            tags = list(analysis.tags or [])
            vector = embedder.embed(
                embedding_text(analysis.summary_zh, analysis.summary_en, tags, document.title)
            )
            session.add(
                Embedding(
                    analysis_id=analysis.id,
                    document_id=document.id,
                    model=embedder.name,
                    dim=len(vector),
                    vec=vector,
                )
            )
            await session.flush()
            await attach_cluster(session, document=document, vec=vector, key_terms=tags[:3])
            stats["embedded"] = int(stats["embedded"]) + 1

        await session.flush()
        stats["clusters"] = int(
            (await session.execute(select(func.count()).select_from(Cluster))).scalar_one()
        )
        stats["multi_doc_clusters"] = int(
            (
                await session.execute(
                    select(func.count()).select_from(Cluster).where(Cluster.doc_count > 1)
                )
            ).scalar_one()
        )
        stats["largest_cluster"] = int(
            (await session.execute(select(func.max(Cluster.doc_count)))).scalar_one() or 0
        )

    return stats


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 结构不符合预期（应为映射）")
    return data


async def _seed(path: pathlib.Path, *, prune: bool = False) -> dict[str, int]:
    from sqlalchemy import select, update

    from app.db import session_scope
    from app.models.source import Source

    data = _load_yaml(path)
    defaults = data.get("defaults") or {}
    entries = data.get("sources") or []
    created = 0
    updated = 0
    skipped = 0
    disabled = 0

    async with session_scope() as session:
        for entry in entries:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            name = str(entry.get("name") or "").strip()
            url = str(entry.get("url") or "").strip()
            if not name or not url:
                skipped += 1
                continue
            existing = (
                await session.execute(select(Source).where(Source.name == name))
            ).scalar_one_or_none()
            target = existing or Source(name=name, kind=str(entry.get("kind") or "rss"), url=url)
            target.kind = str(entry.get("kind") or target.kind)
            target.url = url
            target.tier = int(entry.get("tier", 2))
            target.cadence_minutes = int(
                entry.get("cadence_minutes", defaults.get("cadence_minutes", 60))
            )
            target.enabled = bool(entry.get("enabled", defaults.get("enabled", True)))
            target.license_note = entry.get("license")
            target.params = dict(entry.get("params") or {})
            if existing is None:
                session.add(target)
                created += 1
            else:
                updated += 1
        await session.flush()
        if prune:
            # sources.yaml 是数据源的唯一事实来源：清单外的源一律停用
            names = [
                str(entry.get("name"))
                for entry in entries
                if isinstance(entry, dict) and entry.get("name")
            ]
            if names:
                result = await session.execute(
                    update(Source).where(Source.name.not_in(names)).values(enabled=False)
                )
                # Result 在类型上没有 rowcount，用 getattr 取值（mypy 友好）
                disabled = int(getattr(result, "rowcount", 0) or 0)
        await session.flush()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "disabled": disabled,
    }


def _demo_items(run_token: str) -> list[Any]:
    from app.collectors.base import RawItem

    body_a = (
        "边境地区连续第三天发生交火，双方均报告有平民伤亡。当地医院称收治了 27 名伤者，"
        "两个村庄的居民开始向北部撤离。国际组织呼吁开放人道救援通道，"
        f"并强调物资车队已在附近待命。参考编号 {run_token}"
    )
    body_b = (
        "研究团队在预印本平台发布了新的固态电解质数据，称在室温下将离子电导率提高约三倍。"
        "独立研究者提醒该结果尚未经过同行评审，重复实验仍在进行，"
        f"工业界关注其量产可行性。参考编号 {run_token}"
    )
    return [
        RawItem(
            url=f"https://demo.humanpulse.local/{run_token}/conflict",
            title="边境冲突第三日：平民伤亡与撤离",
            summary=body_a,
            kind="news",
        ),
        RawItem(
            url=f"https://demo.humanpulse.local/{run_token}/science",
            title="室温固态电解质数据引发讨论",
            summary=body_b,
            kind="report",
        ),
        # 与第一条几乎一致的镜像，用来验证 SimHash 前置去重
        RawItem(
            url=f"https://demo.humanpulse.local/{run_token}/conflict-mirror",
            title="边境冲突第三日：平民伤亡与撤离",
            summary=body_a,
            kind="news",
        ),
    ]


async def _demo() -> dict[str, Any]:
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models.analysis import Cluster
    from app.models.document import Document
    from app.models.source import Source
    from app.pipeline.ingest import ingest_items
    from app.pipeline.process import process_pending

    # 冒烟默认不联网、不花钱：显式设为 fake/hash（显式传入的环境变量优先）
    os.environ.setdefault("LLM_PROVIDER", "fake")
    os.environ.setdefault("EMBEDDING_PROVIDER", "hash")

    run_token = uuid.uuid4().hex[:8]
    async with session_scope() as session:
        source = (
            await session.execute(select(Source).where(Source.name == DEMO_SOURCE_NAME))
        ).scalar_one_or_none()
        if source is None:
            source = Source(
                name=DEMO_SOURCE_NAME,
                kind="rss",
                url="https://demo.humanpulse.local/feed.xml",
                tier=3,
                license_note="合成数据，仅用于冒烟测试",
            )
            session.add(source)
            await session.flush()

        ingest = await ingest_items(
            session, source=source, fetch_run_id=None, items=_demo_items(run_token)
        )
        process = await process_pending(session, limit=10)
        await session.flush()
        document_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(Document).where(Document.status == "enriched")
                )
            ).scalar_one()
        )
        cluster_count = int(
            (await session.execute(select(func.count()).select_from(Cluster))).scalar_one()
        )

    return {
        "run_token": run_token,
        "ingest": ingest.as_dict(),
        "process": process.as_dict(),
        "enriched_documents": document_count,
        "clusters": cluster_count,
    }


def _migrate() -> dict[str, str]:
    from alembic.config import Config

    from alembic import command

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
    return {"migrated": "head"}


def cmd_seed(args: argparse.Namespace) -> int:
    result = asyncio.run(_seed(pathlib.Path(args.file), prune=args.prune))
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    result = asyncio.run(_demo())
    print(json.dumps(result, ensure_ascii=False))
    return 0


async def _brief(kind: str, force: bool) -> dict[str, Any]:
    from app.db import session_scope
    from app.workers.jobs import run_brief

    async with session_scope() as session:
        return await run_brief(session, kind=kind, force=force)


def cmd_brief(args: argparse.Namespace) -> int:
    print(json.dumps(asyncio.run(_brief(args.kind, args.force)), ensure_ascii=False))
    return 0


async def _reprice() -> dict[str, Any]:
    """按当前定价表重算历史成本。

    历史行没有记录缓存命中/未命中的拆分，因此输入一律按未命中计——这是**成本上界**。
    简报历史行没有存 token，无法重算，跳过。
    """
    from datetime import UTC, datetime
    from decimal import Decimal as _Decimal

    from sqlalchemy import select

    from app.db import session_scope
    from app.llm.pricing import cost_usd
    from app.models.analysis import Analysis
    from app.models.ops import LlmUsageDay

    # 用固定低谷时刻作基准，避免重算结果随"现在是否高峰"漂移
    reference = datetime(2026, 1, 4, 3, 0, tzinfo=UTC)

    async with session_scope() as session:
        usage_rows = (await session.execute(select(LlmUsageDay))).scalars().all()
        for row in usage_rows:
            row.cost_usd = cost_usd(
                row.model,
                cache_hit_tokens=0,
                cache_miss_tokens=row.tokens_in,
                output_tokens=row.tokens_out,
                moment=reference,
            )
        analyses = (await session.execute(select(Analysis))).scalars().all()
        for analysis in analyses:
            analysis.cost_usd = cost_usd(
                analysis.model,
                cache_hit_tokens=0,
                cache_miss_tokens=analysis.tokens_in,
                output_tokens=analysis.tokens_out,
                moment=reference,
            )
        await session.flush()
        return {
            "usage_rows": len(usage_rows),
            "usage_total_usd": float(sum((row.cost_usd for row in usage_rows), _Decimal(0))),
            "analyses": len(analyses),
            "analyses_total_usd": float(
                sum((analysis.cost_usd for analysis in analyses), _Decimal(0))
            ),
            "note": "输入按未命中计，属成本上界",
        }


async def _backfill_entities() -> dict[str, Any]:
    """把历史 analyses.entities（JSONB）回填进 entities/entity_mentions（幂等）。"""
    from sqlalchemy import select

    from app.db import session_scope
    from app.models.analysis import Analysis
    from app.models.document import Document
    from app.pipeline.entities import upsert_entities

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Analysis, Document)
                .join(Document, Document.id == Analysis.document_id)
                .where(Document.status == "enriched")
                .order_by(Analysis.id.asc())
            )
        ).all()
        scanned = len(rows)
        processed = 0
        written = 0
        for analysis, document in rows:
            items = analysis.entities or []
            if not isinstance(items, list) or not items:
                continue
            payload = [item for item in items if isinstance(item, dict)]
            if not payload:
                continue
            written += await upsert_entities(
                session, document=document, analysis_id=analysis.id, entities=payload
            )
            processed += 1
        await session.flush()
        return {
            "analyses_scanned": scanned,
            "analyses_with_entities": processed,
            "entity_entries": written,
        }


async def _alias_apply(path: str | None) -> dict[str, Any]:
    """应用实体别名表：把「中国 / China」这类写法合并成一个实体（幂等）。"""
    import pathlib as _pathlib

    from app.db import session_scope
    from app.pipeline.aliases import apply_alias_groups, load_alias_groups

    groups = load_alias_groups(_pathlib.Path(path) if path else None)
    async with session_scope() as session:
        stats = await apply_alias_groups(session, groups)
    stats["loaded_groups"] = len(groups)
    return stats


async def _entity_candidates(min_shared: int, limit: int) -> dict[str, Any]:
    """列出疑似同一实体的候选对（同类型 + 同文档共现 + 中英混写），供人工确认。"""
    from app.db import session_scope
    from app.pipeline.aliases import find_alias_candidates

    async with session_scope() as session:
        candidates = await find_alias_candidates(session, min_shared_docs=min_shared, limit=limit)
    return {"count": len(candidates), "candidates": candidates}


async def _video(
    brief_id: int | None,
    language: str,
    out_dir: str,
    render: bool,
    font: str | None,
    voice: bool = False,
) -> dict[str, Any]:
    """生成视频脚本与字幕；render=True 时再调 ffmpeg 出 MP4；voice=True 时做配音。

    配音会**用真实音频时长覆盖脚本里的估算时长**，这样字幕/画面/旁白才对得上。
    """
    from sqlalchemy import select

    from app.briefs.schema import BriefContent
    from app.config import get_settings
    from app.db import session_scope
    from app.models.summary import Brief
    from app.video.render import RenderError, ffmpeg_path, render_video
    from app.video.srt import render_srt
    from app.video.storyboard import build_storyboard

    async with session_scope() as session:
        if brief_id is None:
            brief = (
                await session.execute(select(Brief).order_by(Brief.period_start.desc()).limit(1))
            ).scalar_one_or_none()
        else:
            brief = await session.get(Brief, brief_id)
        if brief is None:
            raise SystemExit("找不到简报，先用 make brief 生成一期")
        payload = brief.structured if isinstance(brief.structured, dict) else {}
        if "sections" not in payload:
            raise SystemExit("这期简报没有结构化内容，无法生成脚本")
        content = BriefContent.model_validate(payload)
        # 复用已入库的简报内容，不重新调用模型，因此不产生费用
        from app.api.v1.briefs import _load_items

        items = await _load_items(session, brief.id)
        storyboard = build_storyboard(
            content, language=language, brief_id=brief.id, kind=brief.kind, items=items
        )

    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    stem = f"brief-{storyboard.brief_id}-{storyboard.language}"
    story_path = target / f"{stem}-storyboard.json"
    srt_path = target / f"{stem}.srt"
    story_path.write_text(
        json.dumps(storyboard.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    srt_path.write_text(render_srt(storyboard), encoding="utf-8")

    result: dict[str, Any] = {
        "brief_id": storyboard.brief_id,
        "language": storyboard.language,
        "scenes": len(storyboard.scenes),
        "total_seconds": storyboard.total_seconds,
        "storyboard": str(story_path),
        "subtitles": str(srt_path),
    }
    audio_path: pathlib.Path | None = None
    if voice:
        from app.video.tts import (
            TtsError,
            apply_audio_durations,
            concat_audio,
            get_tts,
            narrate,
        )

        provider = get_tts()
        if provider is None:
            result["voice_error"] = (
                "未配置 TTS（TTS_PROVIDER=none）：跳过配音。"
                "macOS 本机可设 TTS_PROVIDER=macos-say；Linux 用 TTS_PROVIDER=command + TTS_COMMAND"
            )
        elif not provider.available():
            result["voice_error"] = f"TTS 提供方 {provider.name} 在当前环境不可用"
        else:
            try:
                clips = narrate(storyboard, target / "voice", provider)
                apply_audio_durations(storyboard, clips)
                merged = concat_audio(clips, storyboard, target / f"{stem}-audio.wav")
                # 时长被改写了，脚本与字幕要重新落盘，否则与成片不一致
                story_path.write_text(
                    json.dumps(storyboard.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                srt_path.write_text(render_srt(storyboard), encoding="utf-8")
                audio_path = merged
                result["voice"] = {
                    "provider": provider.name,
                    "clips": len(clips),
                    "audio": str(merged) if merged else None,
                }
            except TtsError as exc:
                result["voice_error"] = str(exc)

    if render:
        if ffmpeg_path() is None:
            result["render_error"] = "未找到 ffmpeg：脚本与字幕已生成，装好后重跑 --render 即可"
        else:
            try:
                result["video"] = render_video(
                    storyboard,
                    target,
                    font=font,
                    audio_path=audio_path,
                    theme_name=get_settings().video_theme,
                )
            except RenderError as exc:
                result["render_error"] = str(exc)
    return result


def cmd_video(args: argparse.Namespace) -> int:
    langs = ("zh", "en") if args.lang == "both" else (args.lang,)
    results = [
        asyncio.run(_video(args.brief, lang, args.out, args.render, args.font, args.voice))
        for lang in langs
    ]
    print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False))
    return 0


def cmd_alias_apply(args: argparse.Namespace) -> int:
    print(json.dumps(asyncio.run(_alias_apply(args.file)), ensure_ascii=False))
    return 0


def cmd_entity_candidates(args: argparse.Namespace) -> int:
    result = asyncio.run(_entity_candidates(args.min_shared, args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_backfill_entities(args: argparse.Namespace) -> int:
    print(json.dumps(asyncio.run(_backfill_entities()), ensure_ascii=False))
    return 0


def cmd_reprice(args: argparse.Namespace) -> int:
    print(json.dumps(asyncio.run(_reprice()), ensure_ascii=False))
    return 0


def cmd_reembed(args: argparse.Namespace) -> int:
    print(json.dumps(asyncio.run(_reembed()), ensure_ascii=False))
    return 0


def cmd_eval_judgement(args: argparse.Namespace) -> int:
    """评估判官在客观子问题上的概率质量（推演上线前的门禁）。"""
    import json

    from app.db import get_sessionmaker
    from app.eval.judgement import run_evaluation

    async def _run() -> dict[str, object]:
        factory = get_sessionmaker()
        async with factory() as session:
            report = await run_evaluation(
                session,
                horizon_days=args.horizon_days,
                sample=args.sample,
                order=args.order,
            )
        return report.as_dict()

    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入 {out}", file=sys.stderr)
    # 未过门时以非零码退出，方便直接用在脚本/CI 里
    return 0 if payload.get("passed") else 2


def cmd_tune_judgement(args: argparse.Namespace) -> int:
    """措辞对照 + Platt 校准实验（校准集拟合，锁定测试集报告）。"""
    import json

    from app.db import get_sessionmaker
    from app.eval.experiment import run_experiment

    async def _run() -> dict[str, object]:
        factory = get_sessionmaker()
        async with factory() as session:
            report = await run_experiment(
                session, horizon_days=args.horizon_days, sample=args.sample
            )
        return report.as_dict()

    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("报告已写入 " + str(out), file=sys.stderr)
    return 0


def cmd_eval_alignment(args: argparse.Namespace) -> int:
    """用人工别名表评估判官的实体对齐能力（分类任务）。"""
    import json

    from app.db import get_sessionmaker
    from app.eval.alignment import run_alignment_eval

    async def _run() -> dict[str, object]:
        factory = get_sessionmaker()
        async with factory() as session:
            report = await run_alignment_eval(session, use_context=args.use_context)
        return report.as_dict()

    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("报告已写入 " + str(out), file=sys.stderr)
    return 0 if payload.get("passed") else 2


def cmd_alias_adjudicate(args: argparse.Namespace) -> int:
    """用判官裁决启发式实体别名候选（两段式：启发式召回 + 判官裁决）。"""
    import json

    from app.db import get_sessionmaker
    from app.pipeline.alias_adjudication import adjudicate_candidates

    async def _run() -> dict[str, object]:
        factory = get_sessionmaker()
        async with factory() as session:
            report = await adjudicate_candidates(
                session, limit=args.limit, min_shared_docs=args.min_shared
            )
        return report.as_dict()

    payload = asyncio.run(_run())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    print(json.dumps(_migrate(), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="humanpulse 运维命令")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="导入数据源清单")
    seed.add_argument("--file", default="../infra/seed/sources.yaml")
    seed.add_argument(
        "--prune",
        action="store_true",
        help="把清单之外的数据源停用（sources.yaml 为唯一事实来源）",
    )
    seed.set_defaults(func=cmd_seed)

    demo = sub.add_parser("demo", help="用合成数据跑通采集与处理（CI 冒烟）")
    demo.set_defaults(func=cmd_demo)

    reembed = sub.add_parser("reembed", help="用当前向量模型重新嵌入并重建聚类（幂等）")
    reembed.set_defaults(func=cmd_reembed)

    brief_parser = sub.add_parser("brief", help="生成日报/周报（默认该周期已有则跳过）")
    brief_parser.add_argument("--kind", choices=["daily", "weekly"], default="daily")
    brief_parser.add_argument("--force", action="store_true")
    brief_parser.set_defaults(func=cmd_brief)

    reprice_parser = sub.add_parser(
        "reprice", help="按当前定价表重算历史成本（输入按未命中计，上界）"
    )
    reprice_parser.set_defaults(func=cmd_reprice)

    backfill_parser = sub.add_parser(
        "backfill-entities", help="把历史 analyses.entities 回填到实体表（幂等）"
    )
    backfill_parser.set_defaults(func=cmd_backfill_entities)

    alias_parser = sub.add_parser("alias-apply", help="应用实体别名表（合并中国/China 这类写法）")
    alias_parser.add_argument("--file", default=None)
    alias_parser.set_defaults(func=cmd_alias_apply)

    video_parser = sub.add_parser("video", help="生成视频脚本与字幕（--render 时用 ffmpeg 出 MP4）")
    video_parser.add_argument("--brief", type=int, default=None, help="简报 id，缺省最新一期")
    video_parser.add_argument("--lang", choices=("zh", "en", "both"), default="zh")
    video_parser.add_argument("--out", default=".cache/video", help="输出目录")
    video_parser.add_argument("--render", action="store_true", help="调用 ffmpeg 渲染 MP4")
    video_parser.add_argument("--font", default=None, help="中文字体文件路径")
    video_parser.add_argument(
        "--voice", action="store_true", help="生成旁白配音（TTS_PROVIDER=macos-say 或 command）"
    )
    video_parser.set_defaults(func=cmd_video)

    candidates_parser = sub.add_parser("entity-candidates", help="列出疑似同一实体的候选对")
    candidates_parser.add_argument("--min-shared", type=int, default=2)
    candidates_parser.add_argument("--limit", type=int, default=30)
    candidates_parser.set_defaults(func=cmd_entity_candidates)

    eval_parser = sub.add_parser(
        "eval-judgement",
        help="评估判官的概率质量（Brier 技能分 / ECE / 可靠性 / 风险-覆盖）",
    )
    eval_parser.add_argument("--horizon-days", type=int, default=7)
    eval_parser.add_argument("--sample", type=int, default=200)
    eval_parser.add_argument(
        "--order",
        choices=("random", "prominent"),
        default="random",
        help="random=全体实体均匀抽样（门禁用）；prominent=最显眼实体（更难的检验）",
    )
    eval_parser.add_argument("--out", default="", help="把 JSON 报告写到指定路径")
    eval_parser.set_defaults(func=cmd_eval_judgement)

    tune_parser = sub.add_parser(
        "tune-judgement",
        help="措辞对照 + Platt 校准（校准集拟合，锁定测试集报告）",
    )
    tune_parser.add_argument("--horizon-days", type=int, default=7)
    tune_parser.add_argument("--sample", type=int, default=300)
    tune_parser.add_argument("--out", default="")
    tune_parser.set_defaults(func=cmd_tune_judgement)

    align_parser = sub.add_parser(
        "eval-alignment",
        help="用人工别名表评估实体对齐（金标准为人工标注，非模型生成）",
    )
    align_parser.add_argument("--out", default="")
    align_parser.add_argument(
        "--use-context",
        action="store_true",
        help="把每边的最近报道标题也塞进 prompt（默认关；实测会让 Laya 排序反转，仅实验用）",
    )
    align_parser.set_defaults(func=cmd_eval_alignment)

    adjudicate_parser = sub.add_parser(
        "alias-adjudicate",
        help="用判官裁决实体别名候选（需 JUDGEMENT_PROVIDER != none）",
    )
    adjudicate_parser.add_argument("--limit", type=int, default=30)
    adjudicate_parser.add_argument("--min-shared", type=int, default=2)
    adjudicate_parser.add_argument("--out", default="")
    adjudicate_parser.set_defaults(func=cmd_alias_adjudicate)

    migrate = sub.add_parser("migrate", help="执行数据库迁移到 head")
    migrate.set_defaults(func=cmd_migrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
