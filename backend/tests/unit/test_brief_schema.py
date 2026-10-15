"""简报 schema 里的深挖分面：结构校验、上限、空壳过滤与向后兼容。

深挖卡片的内容由**简报生成的那次 LLM 调用**产出并存库，视频链路只读库存字段；
因此这里的校验器必须足够宽容——模型偶尔会交回字符串、单个对象或空壳分面，
不能让整期简报因为这个可选字段校验失败。
"""

from __future__ import annotations

from app.briefs.schema import (
    MAX_DEEP_DIVE_FACETS,
    BriefContent,
    DeepDive,
    DeepDiveFacet,
)


def test_brief_without_deep_dive_is_valid() -> None:
    """老简报没有 deep_dive 字段，必须照样能校验（向后兼容）。"""
    content = BriefContent(title_zh="标题")
    assert content.deep_dive is None


def test_deep_dive_facets_are_cleaned() -> None:
    dive = DeepDive(
        title="  事件  标题 ",
        facets=[{"label": " 官方  回应 ", "body": "正文\n换行"}],
    )
    assert dive.title == "事件 标题"
    assert dive.facets[0].label == "官方 回应"
    assert dive.facets[0].body == "正文 换行"


def test_deep_dive_caps_facet_count() -> None:
    facets = [{"label": f"角度{index}", "body": "正文"} for index in range(12)]
    dive = DeepDive(facets=facets)
    assert len(dive.facets) == MAX_DEEP_DIVE_FACETS


def test_deep_dive_tolerates_junk_facets() -> None:
    """字符串、None、数字等混杂项丢弃而不是报错。"""
    dive = DeepDive(facets=["不是对象", None, 42, {"label": "好", "body": "正文"}])  # type: ignore[list-item]
    assert len(dive.facets) == 1
    assert dive.facets[0].label == "好"


def test_deep_dive_accepts_single_object() -> None:
    """模型只给一个对象而不是数组时，也要接住。"""
    dive = DeepDive(facets={"label": "官方回应", "body": "正文"})  # type: ignore[arg-type]
    assert len(dive.facets) == 1


def test_usable_facets_drops_empty_bodies() -> None:
    dive = DeepDive(
        facets=[
            {"label": "官方回应", "body": "有正文"},
            {"label": "只有标题", "body": "   "},
            {"label": "", "body": "只有正文也可以"},
        ]
    )
    usable = dive.usable_facets()
    assert [facet.label for facet in usable] == ["官方回应", ""]


def test_usable_facets_capped() -> None:
    dive = DeepDive(facets=[{"label": f"l{index}", "body": "正文"} for index in range(9)])
    assert len(dive.usable_facets()) == MAX_DEEP_DIVE_FACETS


def test_facet_is_not_empty_when_label_only_has_text() -> None:
    assert DeepDiveFacet(label="官方回应", body="").body == ""
    assert DeepDiveFacet(label="", body="正文").label == ""


def test_brief_content_round_trips_deep_dive() -> None:
    content = BriefContent.model_validate(
        {
            "title_zh": "标题",
            "deep_dive": {
                "title": "深挖事件",
                "facets": [{"label": "监管合作", "body": "监管方已介入调查。"}],
            },
        }
    )
    assert content.deep_dive is not None
    assert content.deep_dive.title == "深挖事件"
    # 存库用的是 model_dump_json，再读回来必须一致
    dumped = content.model_dump_json()
    again = BriefContent.model_validate_json(dumped)
    assert again.deep_dive is not None
    assert again.deep_dive.facets[0].body == "监管方已介入调查。"
