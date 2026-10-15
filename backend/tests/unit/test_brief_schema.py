"""简报 schema 里的深挖分面：结构校验、上限、空壳过滤与向后兼容。

深挖卡片的内容由**简报生成的那次 LLM 调用**产出并存库，视频链路只读库存字段；
因此这里的校验器必须足够宽容——模型偶尔会交回字符串、单个对象或空壳分面，
不能让整期简报因为这个可选字段校验失败。

分面是**双语**的：同一期简报要出中英两版成片，只有一种语言会让另一版中英混排。
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


def test_deep_dive_fields_are_cleaned() -> None:
    dive = DeepDive(
        title_zh="  事件  标题 ",
        title_en="  Event   title ",
        facets=[{"label_zh": " 官方  回应 ", "body_zh": "正文\n换行"}],
    )
    assert dive.title_zh == "事件 标题"
    assert dive.title_en == "Event title"
    assert dive.facets[0].label_zh == "官方 回应"
    assert dive.facets[0].body_zh == "正文 换行"


def test_deep_dive_caps_facet_count() -> None:
    facets = [{"label_zh": f"角度{index}", "body_zh": "正文"} for index in range(12)]
    dive = DeepDive(facets=facets)
    assert len(dive.facets) == MAX_DEEP_DIVE_FACETS


def test_deep_dive_tolerates_junk_facets() -> None:
    """字符串、None、数字等混杂项丢弃而不是报错。"""
    dive = DeepDive(facets=["不是对象", None, 42, {"label_zh": "好", "body_zh": "正文"}])  # type: ignore[list-item]
    assert len(dive.facets) == 1
    assert dive.facets[0].label_zh == "好"


def test_deep_dive_accepts_single_object() -> None:
    """模型只给一个对象而不是数组时，也要接住。"""
    dive = DeepDive(facets={"label_zh": "官方回应", "body_zh": "正文"})  # type: ignore[arg-type]
    assert len(dive.facets) == 1


def test_usable_facets_drops_empty_bodies() -> None:
    dive = DeepDive(
        facets=[
            {"label_zh": "官方回应", "body_zh": "有正文"},
            {"label_zh": "只有标题", "body_zh": "   "},
            {"label_zh": "", "body_zh": "只有正文也可以"},
            {"label_zh": "English only", "body_en": "Body in English"},
        ]
    )
    usable = dive.usable_facets()
    assert [facet.label_zh for facet in usable] == ["官方回应", "", "English only"]


def test_usable_facets_capped() -> None:
    dive = DeepDive(facets=[{"label_zh": f"l{index}", "body_zh": "正文"} for index in range(9)])
    assert len(dive.usable_facets()) == MAX_DEEP_DIVE_FACETS


def test_facet_text_for_language() -> None:
    facet = DeepDiveFacet(
        label_zh="官方回应",
        label_en="Official response",
        body_zh="中文正文",
        body_en="English body",
    )
    assert facet.text_for("zh") == ("官方回应", "中文正文")
    assert facet.text_for("en") == ("Official response", "English body")


def test_facet_text_falls_back_to_the_other_language() -> None:
    """某一种语言缺失时回退另一种：宁可混排，也不要给出空卡。"""
    chinese_only = DeepDiveFacet(label_zh="官方回应", body_zh="中文正文")
    assert chinese_only.text_for("en") == ("官方回应", "中文正文")
    english_only = DeepDiveFacet(label_en="Official", body_en="English body")
    assert english_only.text_for("zh") == ("Official", "English body")


def test_deep_dive_title_for_language() -> None:
    dive = DeepDive(title_zh="中文标题", title_en="English title")
    assert dive.title_for("zh") == "中文标题"
    assert dive.title_for("en") == "English title"
    # 只有一种语言时两边都能取到内容
    only_zh = DeepDive(title_zh="中文标题")
    assert only_zh.title_for("en") == "中文标题"


def test_brief_content_round_trips_deep_dive() -> None:
    content = BriefContent.model_validate(
        {
            "title_zh": "标题",
            "deep_dive": {
                "title_zh": "深挖事件",
                "title_en": "Deep dive event",
                "facets": [
                    {
                        "label_zh": "监管合作",
                        "label_en": "Regulatory",
                        "body_zh": "监管方已介入调查。",
                        "body_en": "Regulators have opened an inquiry.",
                    }
                ],
            },
        }
    )
    assert content.deep_dive is not None
    assert content.deep_dive.title_zh == "深挖事件"
    # 存库用的是 model_dump_json，再读回来必须一致
    again = BriefContent.model_validate_json(content.model_dump_json())
    assert again.deep_dive is not None
    assert again.deep_dive.facets[0].body_zh == "监管方已介入调查。"
    assert again.deep_dive.facets[0].body_en == "Regulators have opened an inquiry."
