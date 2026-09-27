from __future__ import annotations

import math

from app.embedding.hash import HashingEmbedder


def test_same_text_yields_same_vector() -> None:
    embedder = HashingEmbedder(dim=64)
    assert embedder.embed("hello world") == embedder.embed("hello world")


def test_different_text_yields_different_vector() -> None:
    embedder = HashingEmbedder(dim=64)
    assert embedder.embed("hello") != embedder.embed("world")


def test_vector_has_expected_dimension_and_unit_norm() -> None:
    embedder = HashingEmbedder(dim=64)
    vector = embedder.embed("混合 mixed 文本 123")
    assert len(vector) == embedder.dim == 64
    norm = math.sqrt(sum(value * value for value in vector))
    assert abs(norm - 1.0) < 1e-6


def test_empty_string_does_not_raise() -> None:
    embedder = HashingEmbedder(dim=32)
    vector = embedder.embed("")
    assert len(vector) == 32
