"""实体归一：只做同形归一，不跨语言合并——这条边界必须被测试钉住。"""

from __future__ import annotations

from app.pipeline.entities import dedupe_entities, entity_key, normalize_entity_name


def test_normalize_case_and_punctuation() -> None:
    assert normalize_entity_name("Donald  Trump") == "donald trump"
    assert normalize_entity_name("U.S.") == "us"
    assert normalize_entity_name("U.S.") == normalize_entity_name("us")


def test_normalize_fullwidth_and_spaces() -> None:
    # 全角字符先做 NFKC 归一，再去掉多余空白
    assert normalize_entity_name("　ＡＢＣ　") == "abc"
    assert normalize_entity_name("中国    政府") == "中国政府"


def test_normalize_empty_input() -> None:
    assert normalize_entity_name("") == ""
    assert normalize_entity_name("   ") == ""
    assert normalize_entity_name("!!!") == ""


def test_chinese_and_english_are_not_merged() -> None:
    # 这是刻意保留的边界：跨语言别名合并需要别名表/Wikidata，见 ADR-0007
    assert normalize_entity_name("中国") != normalize_entity_name("China")


def test_entity_key_carries_kind() -> None:
    assert entity_key("person", "Donald Trump") == "person:donald trump"
    assert entity_key("PERSON", "Donald Trump") == "person:donald trump"
    assert entity_key("org", "Donald Trump") != entity_key("person", "Donald Trump")
    assert entity_key("", "X") == "org:x"


def test_dedupe_keeps_highest_salience() -> None:
    items = [
        {"name": "China", "kind": "place", "salience": 0.2},
        {"name": "china", "kind": "place", "salience": 0.9},
        {"name": "China", "kind": "place", "salience": 0.5},
    ]
    result = dedupe_entities(items)
    assert len(result) == 1
    assert result[0]["salience"] == 0.9


def test_dedupe_keeps_different_kinds_apart() -> None:
    items = [
        {"name": "Apple", "kind": "org", "salience": 0.5},
        {"name": "Apple", "kind": "place", "salience": 0.3},
    ]
    assert len(dedupe_entities(items)) == 2


def test_dedupe_drops_empty_names() -> None:
    items = [
        {"name": "", "kind": "org", "salience": 0.5},
        {"name": "   ", "kind": "org", "salience": 0.5},
        {"name": "!!!", "kind": "org", "salience": 0.5},
        {"name": "Kept", "kind": "org", "salience": 0.1},
    ]
    result = dedupe_entities(items)
    assert len(result) == 1
    assert result[0]["name"] == "Kept"
