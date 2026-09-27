"""向量化契约。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> list[float]:
        """返回 L2 归一化后的向量（cosine 相似度即点积）。"""
        ...


def l2_normalize(vec: list[float]) -> list[float]:
    import math

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]
