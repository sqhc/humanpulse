"""向量化入口：按配置选择具体实现。"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.embedding.base import Embedder, l2_normalize
from app.embedding.hash import HashingEmbedder
from app.embedding.local import LocalEmbedder

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "LocalEmbedder",
    "get_embedder",
    "l2_normalize",
]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """按 settings.embedding_provider 返回单例 embedder。"""
    settings = get_settings()
    provider = settings.embedding_provider.strip().lower()
    if provider == "hash":
        return HashingEmbedder()
    if provider == "local":
        return LocalEmbedder()
    raise ValueError(
        f"未知的 embedding_provider：{settings.embedding_provider!r}（可选：hash、local）"
    )
