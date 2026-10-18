"""简报 schema 里的深挖分面：结构校验、上限、空壳过滤与向后兼容。

深挖卡片的内容由**简报生成的那次 LLM 调用**产出并存库，视频链路只读库存字段；
因此这里的校验器必须足够宽容——模型偶尔会交回字符串、单个对象或空壳分面，
不能让整期简报因为这个可选字段校验失败。

分面是**双语**的：同一期简报要出中英两版成片，只有一种语言会让另一版中英混排。
"""

from __future__ import annotations

from app.briefs.schema import (
    MAX_DEEP_DIVE_FACETS,
    PULSE_HOOK_FLOOR,
    PULSE_TEXT_BUDGET,
    BriefContent,
    DeepDive,
    DeepDiveFacet,
    PulseCard,
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


def test_pulse_card_fits_total_length_budget() -> None:
    """脉搏短讯的总长预算是「事实 + 钩子」合计，不是单字段上限。

    实测踩过的坑：fact_en 158 + hook_en 179 = 337，两段各自都没超单字段上限，
    合计却超了契约的 ≤280，短讯发出去就是超长文本。
    """
    long_fact_en = (
        "Israeli drone attacks killed six Palestinians across Gaza; UNICEF said more than "
        "340 children have been killed in Gaza since the ceasefire began. (Al Jazeera)"
    )
    long_hook_en = (
        "Continued civilian deaths during the ceasefire highlight the fragility of the "
        "situation; next, watch for any Israeli response and independent verification of "
        "the casualty figures."
    )
    card = PulseCard(
        fact_zh="以色列无人机袭击加沙多地，致6名巴勒斯坦人死亡；UNICEF称停火以来加沙已有超340名儿童丧生。（半岛电视台）",
        fact_en=long_fact_en,
        hook_zh="停火期间持续出现平民伤亡，凸显局势脆弱；接下来需观察以色列方面是否回应，以及伤亡数字能否得到独立核实。",
        hook_en=long_hook_en,
    )

    assert len(card.fact_zh) + len(card.hook_zh) <= PULSE_TEXT_BUDGET
    assert len(card.fact_en) + len(card.hook_en) <= PULSE_TEXT_BUDGET
    # 钩子是差异化的核心，不能被裁成空
    assert card.hook_zh
    assert len(card.hook_en) >= PULSE_HOOK_FLOOR
    assert card.hook_en.endswith("…")


def test_pulse_card_keeps_short_text_untouched() -> None:
    """没超预算时不裁剪，也不该凭空补省略号。"""
    card = PulseCard(
        section_key="conflict",
        fact_zh="事实一句。",
        fact_en="One fact.",
        hook_zh="为什么重要。",
        hook_en="Why it matters.",
    )
    assert card.fact_zh == "事实一句。"
    assert card.hook_en == "Why it matters."
    assert "…" not in card.fact_en


def test_pulse_card_trims_leading_fact_when_hook_needs_floor() -> None:
    """事实占满预算时，保住钩子下限、改裁事实，而不是把钩子压没。"""
    card = PulseCard(
        fact_zh="事实" * 200,
        fact_en="word " * 200,
        hook_zh="钩子" * 100,
        hook_en="hook " * 100,
    )
    assert len(card.fact_zh) + len(card.hook_zh) <= PULSE_TEXT_BUDGET
    assert len(card.fact_en) + len(card.hook_en) <= PULSE_TEXT_BUDGET
    # 钩子不能被子句压没；英文允许差几个字符——词边界优先于精确下限
    assert len(card.hook_zh) >= PULSE_HOOK_FLOOR
    assert len(card.hook_en) >= PULSE_HOOK_FLOOR - 10
