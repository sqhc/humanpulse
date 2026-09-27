from __future__ import annotations

import pytest

from app.llm.prompts import load_prompt


@pytest.mark.parametrize("kind", ["news", "discussion", "report"])
def test_each_prompt_has_placeholders(kind: str) -> None:
    text = load_prompt(kind)
    assert "{title}" in text
    assert "{text}" in text
    assert "{url}" in text


def test_unknown_kind_falls_back_to_news() -> None:
    assert load_prompt("does-not-exist") == load_prompt("news")


def test_prompts_are_distinct() -> None:
    assert load_prompt("news") != load_prompt("discussion")
    assert load_prompt("discussion") != load_prompt("report")
