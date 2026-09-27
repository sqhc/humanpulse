from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schema import AnalysisOut


def test_tags_from_comma_string_are_normalized() -> None:
    out = AnalysisOut(relevant=True, score=10, tags="A, b")
    assert out.tags == ["a", "b"]


def test_tags_are_deduplicated_in_order() -> None:
    out = AnalysisOut(relevant=True, score=10, tags=["A", "a", "B", " b "])
    assert out.tags == ["a", "b"]


def test_tags_are_truncated_to_eight() -> None:
    tags = [f"t{i}" for i in range(12)]
    out = AnalysisOut(relevant=True, score=10, tags=tags)
    assert len(out.tags) == 8
    assert out.tags == tags[:8]


def test_entities_as_string_list_are_normalized() -> None:
    out = AnalysisOut(relevant=True, score=10, entities=["OpenAI", "European Union"])
    assert [entity.name for entity in out.entities] == ["OpenAI", "European Union"]
    assert all(entity.kind == "org" for entity in out.entities)


def test_score_above_100_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalysisOut(relevant=True, score=101)


def test_regions_are_truncated_to_six() -> None:
    regions = [f"r{i}" for i in range(9)]
    out = AnalysisOut(relevant=True, score=10, regions=regions)
    assert len(out.regions) == 6
    assert out.regions == regions[:6]
