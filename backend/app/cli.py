"""运维 CLI：python -m app.cli <command>"""

from __future__ import annotations

import argparse
import pathlib
import sys


def cmd_seed(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.file)
    if not path.exists():
        print(f"找不到源清单：{path}", file=sys.stderr)
        return 1
    entries = sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("- ")
    )
    print(f"源清单 {path} 可读，包含 {entries} 个顶层条目。")
    print("Phase 1 起该命令会把源写入 sources 表（当前为骨架校验）。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="humanpulse 运维命令")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="导入数据源清单")
    seed.add_argument("--file", default="../infra/seed/sources.yaml")
    seed.set_defaults(func=cmd_seed)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
