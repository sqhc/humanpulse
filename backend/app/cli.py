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
import uuid
from typing import Any

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO_SOURCE_NAME = "demo (synthetic)"


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 结构不符合预期（应为映射）")
    return data


async def _seed(path: pathlib.Path) -> dict[str, int]:
    from sqlalchemy import select

    from app.db import session_scope
    from app.models.source import Source

    data = _load_yaml(path)
    defaults = data.get("defaults") or {}
    entries = data.get("sources") or []
    created = 0
    updated = 0
    skipped = 0

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

    return {"created": created, "updated": updated, "skipped": skipped}


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
    result = asyncio.run(_seed(pathlib.Path(args.file)))
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    result = asyncio.run(_demo())
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    print(json.dumps(_migrate(), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="humanpulse 运维命令")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="导入数据源清单")
    seed.add_argument("--file", default="../infra/seed/sources.yaml")
    seed.set_defaults(func=cmd_seed)

    demo = sub.add_parser("demo", help="用合成数据跑通采集与处理（CI 冒烟）")
    demo.set_defaults(func=cmd_demo)

    migrate = sub.add_parser("migrate", help="执行数据库迁移到 head")
    migrate.set_defaults(func=cmd_migrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
