"""确定性哈希向量化：仅用于开发/CI，不具备真正的语义能力。"""

from __future__ import annotations

import hashlib
import re

from app.config import get_settings
from app.embedding.base import l2_normalize

_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    """ASCII 词转小写；连续汉字切成单字与相邻双字。"""
    tokens = [match.group(0).lower() for match in _ASCII_WORD.finditer(text)]
    for match in _CJK_RUN.finditer(text):
        run = match.group(0)
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


class HashingEmbedder:
    """基于 blake2b 的哈希向量化。

    它只是把 token 确定性地散列到固定维度，能保证相同文本得到相同向量，
    但**不具备真正的语义能力**：近义词不会自动靠近。
    因此仅用于开发、CI 与离线演示，生产环境请使用 embedding_provider=local。
    """

    name: str
    dim: int

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim if dim is not None else get_settings().embedding_dim
        self.name = f"hash-{self.dim}"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            first = value % self.dim
            second = (value // self.dim) % self.dim
            vector[first] += 1.0
            # 第二个索引带符号位，让不同 token 可以相互抵消，避免向量过度同向。
            vector[second] += 1.0 if (value >> 63) & 1 else -1.0
        return l2_normalize(vector)
