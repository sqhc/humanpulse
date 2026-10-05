"""别名表的读写与「候选确认」支撑逻辑。

与 aliases.py 的分工：
- `aliases.py` 负责**用**别名表（解析、合并、找候选）；
- `alias_table.py` 负责**改**别名表（把确认过的候选写回 YAML）与结构校验。

写回是整文件重写：保留注释需要额外依赖（ruamel 之类），而这张表是人工维护的短文件，
格式由本模块统一渲染，保证 diff 稳定可读。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.pipeline.aliases import AliasGroup, alias_file_path, load_alias_groups

HEADER = (
    "# 实体别名表：把同一实体的不同写法合并成一条记录。\n"
    "#\n"
    "# 为什么需要它：归一化（app/pipeline/entities.py）只做同形合并（大小写/全角/标点），\n"
    "# 「中国」「中國」「China」在数据库里是三条记录——时间线因此看起来比实际更碎。\n"
    "# 跨语言、简繁、缩写、俗称必须靠人工（或 Wikidata）定义，本文件就是那层人工知识。\n"
    "#\n"
    "# 规则：\n"
    "#   * canonical 是保留下来对外展示的名字（大小写按此原样保留）；\n"
    "#   * aliases 里任何写法命中后都会指向 canonical；\n"
    "#   * 简繁两种写法都要列（「中国」与「中國」不会自动归一）；\n"
    "#   * 不要放有歧义的词（例如 苹果 = 水果 or 公司、Mercury = 行星 or 人名），\n"
    "#     宁可漏合并也不要错误合并——错误合并会把两个实体的事件混在一起；\n"
    "#   * 剩余的可疑写法在管理台（#/admin 的「实体候选」）或 `make entity-candidates` 里找。\n"
    "#\n"
    "# 本文件可以被管理台写回（POST /admin/entity-aliases/apply?remember=true），\n"
    "# 写回时整文件重建，排序与注释由本模块保证稳定。\n"
    "#\n"
    "groups:\n"
)

VALID_KINDS = ("person", "org", "place", "event")


@dataclass(frozen=True, slots=True)
class EntityRef:
    """合并时需要的最小实体信息（与 ORM 解耦，便于单测）。"""

    id: int
    name: str
    kind: str
    aliases: tuple[str, ...] = ()


def groups_from_merges(
    merges: list[dict[str, Any]], refs: dict[int, EntityRef]
) -> tuple[list[AliasGroup], list[str]]:
    """把管理台提交的 {canonical_id, alias_ids[]} 变成 AliasGroup，返回 (组, 错误列表)。

    纯函数：不碰数据库，异常都以错误字符串返回，由调用方决定 HTTP 状态码。
    """
    groups: list[AliasGroup] = []
    errors: list[str] = []
    seen_canonical: set[str] = set()
    for index, merge in enumerate(merges):
        canonical_id = merge.get("canonical_id")
        alias_ids = merge.get("alias_ids") or []
        canonical = refs.get(int(canonical_id)) if canonical_id is not None else None
        if canonical is None:
            errors.append(f"merges[{index}]: 规范实体 {canonical_id} 不存在")
            continue
        if not alias_ids:
            errors.append(f"merges[{index}]: 没有给出别名实体")
            continue
        aliases: list[str] = []
        for alias_id in alias_ids:
            alias = refs.get(int(alias_id))
            if alias is None:
                errors.append(f"merges[{index}]: 别名实体 {alias_id} 不存在")
                continue
            if alias.id == canonical.id:
                errors.append(f"merges[{index}]: 别名与规范实体是同一个（id={alias.id}）")
                continue
            if alias.kind != canonical.kind:
                # 类型不同几乎肯定是误合并（person vs place），拒绝而不是猜
                errors.append(
                    f"merges[{index}]: 类型不一致（{canonical.kind} vs {alias.kind}，"
                    f"{canonical.name} / {alias.name}）"
                )
                continue
            aliases.extend([alias.name, *alias.aliases])
        if not aliases:
            continue
        dedup_key = f"{canonical.kind}:{canonical.name.strip().lower()}"
        if dedup_key in seen_canonical:
            errors.append(f"merges[{index}]: 同一个规范实体在一次请求里出现多次")
            continue
        seen_canonical.add(dedup_key)
        groups.append(
            AliasGroup(
                canonical=canonical.name,
                kind=canonical.kind,
                aliases=tuple(dict.fromkeys(aliases)),
            )
        )
    return groups, errors


def merge_into_table(existing: list[AliasGroup], new_groups: list[AliasGroup]) -> list[AliasGroup]:
    """并入现有表：同一 canonical 取别名并集，按 kind+canonical 排序保证 diff 稳定。"""
    merged: dict[str, AliasGroup] = {}
    for group in [*existing, *new_groups]:
        key = group.canonical_key
        current = merged.get(key)
        if current is None:
            # 规范名自己不该出现在别名列表里；新组也要过滤，否则写回 YAML 会自我重复
            fresh = [
                name for name in dict.fromkeys(group.aliases) if name.strip() != group.canonical
            ]
            merged[key] = AliasGroup(group.canonical, group.kind, tuple(fresh))
            continue
        aliases = [*current.aliases, *group.aliases]
        aliases = [name for name in dict.fromkeys(aliases) if name.strip() != current.canonical]
        merged[key] = AliasGroup(current.canonical, current.kind, tuple(aliases))
    return sorted(merged.values(), key=lambda item: (item.kind, item.canonical.lower()))


def _yaml_quote(value: str) -> str:
    """始终双引号：别名里有逗号、冒号、撇号的情况不少（U.S. / People's Republic）。"""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_alias_groups(groups: list[AliasGroup]) -> str:
    """渲染 YAML 文本；只输出已知字段，顺序固定。"""
    out = [HEADER]
    for group in groups:
        out.append(f"  - canonical: {_yaml_quote(group.canonical)}")
        out.append(f"    kind: {group.kind}")
        rendered = ", ".join(_yaml_quote(name) for name in group.aliases)
        out.append(f"    aliases: [{rendered}]")
    return "".join(line + "\n" for line in out)


def write_alias_groups(groups: list[AliasGroup], path: Path | None = None) -> Path:
    """整文件重写别名表（管理台确认候选时调用）。"""
    target = path or alias_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_alias_groups(groups), encoding="utf-8")
    return target


def validate_alias_file(path: Path | None = None) -> list[str]:
    """自检：YAML 可解析、kind 合法、同一个别名没被两个组抢走。"""
    import yaml  # type: ignore[import-untyped]

    target = path or alias_file_path()
    problems: list[str] = []
    if not target.is_file():
        return [f"别名表不存在：{target}"]
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    owner: dict[str, str] = {}
    for index, item in enumerate(payload.get("groups") or []):
        if not isinstance(item, dict):
            problems.append(f"groups[{index}] 不是映射")
            continue
        canonical = str(item.get("canonical") or "").strip()
        kind = str(item.get("kind") or "").strip().lower()
        if not canonical:
            problems.append(f"groups[{index}] 缺少 canonical")
        if kind not in VALID_KINDS:
            problems.append(f"groups[{index}] kind 非法：{kind!r}")
        for name in item.get("aliases") or []:
            cleaned = str(name).strip().lower()
            if not cleaned:
                continue
            previous = owner.get(f"{kind}:{cleaned}")
            if previous is not None and previous != canonical:
                problems.append(f"{name} 同时属于 {previous} 与 {canonical}")
            owner[f"{kind}:{cleaned}"] = canonical
    return problems


def load_validated(path: Path | None = None) -> tuple[list[AliasGroup], list[str]]:
    """读取 + 自检；自检问题不影响读取结果（合并照常执行）。"""
    target = path or alias_file_path()
    return load_alias_groups(target), validate_alias_file(target)
