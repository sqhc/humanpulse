"""把 jev-cookbook 第十章的 serve.py 拉起来（Jev 兼容路由）。

为什么需要这个 launcher：
第十章 serve.py 用的是包内相对导入（from .client import LayaClient），
而它所在的目录名是 10_本地模型 —— 以数字开头且含中文，不是合法的 Python 包名，
既不能用 python -m 也不能直接 python serve.py（会报
attempted relative import with no known parent package）。

这里给那个目录造一个合成包，再按包内模块加载 serve.py，
于是相对导入成立，我们不需要复制或修改上游代码。

用法：
  python scripts/laya_serve.py --chapter-dir <第十章目录> --model-dir <权重> --port 8077
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path

DEFAULT_CHAPTER = (
    "/Users/shenqing/Desktop/Jevstudy/jev-cookbook/main/10_本地模型"
)


def load_chapter_serve(chapter_dir: Path) -> types.ModuleType:
    """把 chapter_dir 变成合成包 laya_chapter，再加载它的 serve 模块。"""
    if not (chapter_dir / "serve.py").is_file():
        raise SystemExit(f"没找到 serve.py：{chapter_dir}")

    package_name = "laya_chapter"
    package = types.ModuleType(package_name)
    package.__path__ = [str(chapter_dir)]
    sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.serve", chapter_dir / "serve.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载 {chapter_dir / 'serve.py'}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="起本地 Laya 判官服务")
    parser.add_argument("--chapter-dir", default=DEFAULT_CHAPTER)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--port", type=int, default=8077)
    parser.add_argument("--host", default="127.0.0.1")
    args, rest = parser.parse_known_args()

    argv = ["serve.py", "--host", args.host, "--port", str(args.port)]
    if args.model_dir:
        argv += ["--model-dir", args.model_dir]
    argv += rest
    sys.argv = argv

    module = load_chapter_serve(Path(args.chapter_dir).expanduser())
    module.main()


if __name__ == "__main__":
    main()
