"""别名表读写：管理台确认候选时会把表写回 YAML，格式必须稳定可解析。"""

from __future__ import annotations

from pathlib import Path

from app.pipeline.alias_table import (
    EntityRef,
    dump_alias_groups,
    groups_from_merges,
    load_validated,
    merge_into_table,
    validate_alias_file,
    write_alias_groups,
)
from app.pipeline.aliases import AliasGroup, load_alias_groups


def _refs() -> dict[int, EntityRef]:
    return {
        1: EntityRef(id=1, name="China", kind="place", aliases=("PRC",)),
        2: EntityRef(id=2, name="中国", kind="place"),
        3: EntityRef(id=3, name="中國", kind="place"),
        4: EntityRef(id=4, name="Al Jazeera", kind="org"),
        5: EntityRef(id=5, name="卡塔尔", kind="place"),
    }


def test_groups_from_merges_builds_group() -> None:
    groups, errors = groups_from_merges([{"canonical_id": 1, "alias_ids": [2, 3]}], _refs())
    assert errors == []
    assert len(groups) == 1
    assert groups[0].canonical == "China"
    assert groups[0].kind == "place"
    # 别名里要包含两边实体名，以及别名实体自己已有的别名（PRC 是规范实体自带的，不重复）
    assert set(groups[0].aliases) == {"中国", "中國"}


def test_groups_from_merges_rejects_kind_mismatch() -> None:
    groups, errors = groups_from_merges([{"canonical_id": 1, "alias_ids": [4]}], _refs())
    assert groups == []
    assert any("类型不一致" in message for message in errors)


def test_groups_from_merges_reports_missing_and_self() -> None:
    groups, errors = groups_from_merges(
        [
            {"canonical_id": 999, "alias_ids": [2]},
            {"canonical_id": 1, "alias_ids": [1]},
            {"canonical_id": 1, "alias_ids": []},
        ],
        _refs(),
    )
    assert groups == []
    joined = " ".join(errors)
    assert "不存在" in joined
    assert "同一个" in joined
    assert "没有给出别名实体" in joined


def test_groups_from_merges_rejects_duplicate_canonical() -> None:
    groups, errors = groups_from_merges(
        [
            {"canonical_id": 1, "alias_ids": [2]},
            {"canonical_id": 1, "alias_ids": [3]},
        ],
        _refs(),
    )
    assert len(groups) == 1
    assert any("出现多次" in message for message in errors)


def test_merge_into_table_dedupes_and_sorts() -> None:
    existing = [AliasGroup("China", "place", ("中国",)), AliasGroup("NATO", "org", ("北约",))]
    incoming = [
        AliasGroup("China", "place", ("中國", "中国")),
        AliasGroup("Al Jazeera", "org", ("半岛电视台",)),
    ]
    merged = merge_into_table(existing, incoming)
    keys = [group.canonical_key for group in merged]
    assert keys == sorted(keys, key=lambda key: (key.split(":")[0], key.split(":")[1]))
    china = next(group for group in merged if group.canonical == "China")
    assert list(china.aliases) == ["中国", "中國"]
    assert len(merged) == 3


def test_merge_into_table_drops_canonical_from_aliases() -> None:
    merged = merge_into_table([], [AliasGroup("China", "place", ("China", "中国"))])
    assert list(merged[0].aliases) == ["中国"]


def test_dump_and_reload_round_trip(tmp_path: Path) -> None:
    groups = [
        AliasGroup("United States", "place", ("美国", "U.S.", "A: B")),
        AliasGroup("China", "place", ("中国",)),
    ]
    target = tmp_path / "aliases.yaml"
    write_alias_groups(groups, target)
    reloaded = load_alias_groups(target)
    assert [(group.canonical, group.kind, tuple(group.aliases)) for group in reloaded] == [
        ("United States", "place", ("美国", "U.S.", "A: B")),
        ("China", "place", ("中国",)),
    ]
    assert validate_alias_file(target) == []


def test_dump_is_deterministic() -> None:
    groups = [AliasGroup("China", "place", ("中国",))]
    assert dump_alias_groups(groups) == dump_alias_groups(groups)


def test_validate_detects_duplicate_alias_owner(tmp_path: Path) -> None:
    target = tmp_path / "bad.yaml"
    target.write_text(
        "groups:\n"
        "  - canonical: China\n"
        "    kind: place\n"
        '    aliases: ["中国"]\n'
        "  - canonical: Taiwan\n"
        "    kind: place\n"
        '    aliases: ["中国"]\n',
        encoding="utf-8",
    )
    problems = validate_alias_file(target)
    assert len(problems) == 1
    assert "同时属于" in problems[0]


def test_validate_detects_bad_kind(tmp_path: Path) -> None:
    target = tmp_path / "bad2.yaml"
    target.write_text(
        'groups:\n  - canonical: X\n    kind: planet\n    aliases: ["Y"]\n', encoding="utf-8"
    )
    assert any("kind 非法" in problem for problem in validate_alias_file(target))


def test_validate_missing_file(tmp_path: Path) -> None:
    assert validate_alias_file(tmp_path / "nope.yaml") != []


def test_shipped_file_loads_without_problems() -> None:
    groups, problems = load_validated()
    assert problems == []
    assert len(groups) >= 20
