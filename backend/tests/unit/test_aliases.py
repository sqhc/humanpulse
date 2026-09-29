"""别名表：把「中国 / China」合并成一条，是时间线可读性的关键（ADR-0009）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.aliases import (
    _index_for,
    alias_file_path,
    is_cjk,
    load_alias_groups,
    resolve_alias,
)
from app.pipeline.entities import entity_key


def test_shipped_alias_file_is_loadable() -> None:
    groups = load_alias_groups()
    assert len(groups) >= 20
    assert all(group.canonical and group.aliases for group in groups)
    keys = [group.canonical_key for group in groups]
    assert len(keys) == len(set(keys)), "规范键不能重复"


def test_chinese_name_resolves_to_english_canonical() -> None:
    key, name = resolve_alias("place", "中国")
    assert name == "China"
    assert key == entity_key("place", "China")


def test_alias_is_kind_sensitive() -> None:
    # 「中国」只作为 place 的别名登记；换成 org 就不该命中
    key, name = resolve_alias("org", "中国")
    assert name == "中国"
    assert key == entity_key("org", "中国")


def test_unknown_name_returns_itself() -> None:
    key, name = resolve_alias("person", "张三")
    assert name == "张三"
    assert key == entity_key("person", "张三")


def test_canonical_name_maps_to_itself() -> None:
    key, name = resolve_alias("place", "China")
    assert name == "China"
    assert key == entity_key("place", "China")


def test_case_and_punctuation_insensitive() -> None:
    # entity_key 会先归一化，所以 U.S. / us / US 都指向 United States
    assert resolve_alias("place", "U.S.")[1] == "United States"
    assert resolve_alias("place", "us")[1] == "United States"


def test_missing_file_is_tolerated(tmp_path: Path) -> None:
    assert load_alias_groups(tmp_path / "nope.yaml") == []


def test_env_override_changes_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "aliases.yaml"
    custom.write_text(
        'groups:\n  - canonical: Foo\n    kind: org\n    aliases: ["福"]\n', encoding="utf-8"
    )
    monkeypatch.setenv("ENTITY_ALIAS_FILE", str(custom))
    _index_for.cache_clear()
    try:
        assert alias_file_path() == custom
        assert resolve_alias("org", "福")[1] == "Foo"
        # 覆盖后，内置表不再生效
        assert resolve_alias("place", "中国")[1] == "中国"
    finally:
        monkeypatch.delenv("ENTITY_ALIAS_FILE", raising=False)
        _index_for.cache_clear()


def test_is_cjk_detects_scripts() -> None:
    assert is_cjk("中国") is True
    assert is_cjk("China") is False
    assert is_cjk("中国新闻网") is True
