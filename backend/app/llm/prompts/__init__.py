"""提示词加载：按 kind 读取同目录下的 markdown 模板。"""

from __future__ import annotations

from pathlib import Path

from app.llm.schema import PROMPT_VERSION

_PROMPT_DIR = Path(__file__).resolve().parent
_DEFAULT_KIND = "news"
# 只有这里登记的 kind 才会被直接读取，其余一律回退 news，避免路径拼接出意外文件。
_KNOWN_KINDS = frozenset({"news", "discussion", "report"})

__all__ = ["PROMPT_VERSION", "load_prompt"]


def load_prompt(kind: str) -> str:
    """读取提示词模板。

    未知 kind 回退到 news；文件缺失时抛 FileNotFoundError，并给出可直接排查的路径。
    """
    normalized = (kind or "").strip().lower()
    if normalized not in _KNOWN_KINDS:
        normalized = _DEFAULT_KIND
    path = _PROMPT_DIR / f"{normalized}.md"
    if not path.is_file():
        raise FileNotFoundError(f"提示词文件不存在：{path}（kind={kind!r}，回退到 {normalized}）")
    return path.read_text(encoding="utf-8")
