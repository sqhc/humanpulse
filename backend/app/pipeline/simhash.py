"""64 位 SimHash：调用 LLM 之前拦截转载与镜像。"""

from __future__ import annotations

import hashlib
import re

MASK64 = (1 << 64) - 1
_SIGNED_MIN = -(1 << 63)

_LATIN_RE = re.compile(r"[0-9a-z]+")
_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def tokenize(text: str) -> list[str]:
    """英文按词、中文按单字 + 相邻双字，兼顾两种语料。"""
    if not text:
        return []
    lowered = text.lower()
    tokens = _LATIN_RE.findall(lowered)
    for run in _CJK_RUN_RE.findall(lowered):
        tokens.extend(run)
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def _token_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def simhash64(text: str) -> int:
    """返回无符号 64 位指纹；空文本返回 0。"""
    tokens = tokenize(text)
    if not tokens:
        return 0
    weights = [0] * 64
    for token in tokens:
        h = _token_hash(token)
        for bit in range(64):
            weights[bit] += 1 if (h >> bit) & 1 else -1
    value = 0
    for bit in range(64):
        if weights[bit] > 0:
            value |= 1 << bit
    return value


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & MASK64).bit_count()


def is_near_duplicate(a: int | None, b: int | None, threshold: int) -> bool:
    if a is None or b is None:
        return False
    return hamming(a, b) <= threshold


def to_signed64(value: int) -> int:
    """PostgreSQL BIGINT 是有符号的，落库前转换。"""
    unsigned = value & MASK64
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def from_signed64(value: int) -> int:
    return value & MASK64
