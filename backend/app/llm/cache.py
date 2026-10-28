"""语义缓存：利用向量空间检索相似请求以降低成本并提高响应速度。"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding import get_embedder

log = structlog.get_logger("llm.cache")


class SemanticCache:
    """基于 pgvector 的语义缓存。"""

    def __init__(self, session: AsyncSession, embedder: Any = None) -> None:
        self.session = session
        self.embedder = embedder or get_embedder()

    async def get(self, prompt: str, threshold: float = 0.95) -> dict[str, Any] | None:
        """检索语义高度相似的缓存结果。"""
        # TODO: 实现向量检索逻辑
        return None

    async def set(self, prompt: str, result: dict[str, Any]) -> None:
        """存储请求结果。"""
        pass
