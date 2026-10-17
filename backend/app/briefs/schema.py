"""简报内容结构：模型必须按这个结构输出，渲染与前端都基于它。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

PROMPT_VERSION = "v1"

SectionKey = Literal["conflict", "science", "labor", "other"]
SECTION_KEYS: tuple[str, ...] = ("conflict", "science", "labor", "other")

# 深挖卡片的张数上限：视频版式是 3 列 × 2 行，多于 6 张会挤爆
MAX_DEEP_DIVE_FACETS = 6

DEFAULT_HEADINGS: dict[str, tuple[str, str]] = {
    "conflict": ("冲突与安全", "Conflict & security"),
    "science": ("科技与科学", "Science & technology"),
    "labor": ("社会运动与劳工", "Social movements & labour"),
    "other": ("其他值得记录", "Also worth noting"),
}


class BriefSection(BaseModel):
    key: SectionKey
    heading_zh: str = Field(default="", max_length=80)
    heading_en: str = Field(default="", max_length=120)
    bullets_zh: list[str] = Field(default_factory=list)
    bullets_en: list[str] = Field(default_factory=list)

    @field_validator("heading_zh", "heading_en")
    @classmethod
    def _fill_heading(cls, value: str, info: object) -> str:
        # 模型偶尔漏标题：用默认标题兜底，避免前端出现空标题分组。
        if value.strip():
            return value.strip()
        key = getattr(info, "data", {}).get("key", "other")
        index = 0 if "zh" in str(getattr(info, "field_name", "")) else 1
        return DEFAULT_HEADINGS.get(str(key), ("其他", "Other"))[index]

    @field_validator("bullets_zh", "bullets_en", mode="before")
    @classmethod
    def _clean_bullets(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = " ".join(str(item).split())
            if text:
                cleaned.append(text[:400])
        return cleaned[:8]


class DeepDiveFacet(BaseModel):
    """深挖卡片的一个分面：小标题 + 一句正文（双语）。

    模型只允许从素材里提取，**没有素材支撑的分面必须省略**，不许凑数。
    双语是必须的：同一个简报要出中英两版成片（`--lang both`），
    分面若只有一种语言，另一种语言的卡片就会中英混排。
    """

    label_zh: str = Field(default="", max_length=40)
    label_en: str = Field(default="", max_length=60)
    body_zh: str = Field(default="", max_length=300)
    body_en: str = Field(default="", max_length=600)

    @field_validator("label_zh", "label_en", "body_zh", "body_en", mode="before")
    @classmethod
    def _clean(cls, value: object) -> str:
        return " ".join(str(value or "").split())

    def has_body(self) -> bool:
        return bool(self.body_zh.strip() or self.body_en.strip())

    def text_for(self, language: str) -> tuple[str, str]:
        """按语言取 (label, body)；该语言缺失时回退另一种，宁可混排也不给空卡。"""
        if language == "en":
            return self.label_en or self.label_zh, self.body_en or self.body_zh
        return self.label_zh or self.label_en, self.body_zh or self.body_en


class DeepDive(BaseModel):
    """对单个事件的深挖：一句标题 + 若干「角度」分面（如官方回应/技术手法/监管合作）。

    分面内容在**简报生成的那次 LLM 调用**里产出并存进 `briefs.structured`，
    视频链路只读库存字段——这样「文案全部来自已入库简报、零模型调用、可复现」的约束不被破坏。
    """

    title_zh: str = Field(default="", max_length=200)
    title_en: str = Field(default="", max_length=200)
    facets: list[DeepDiveFacet] = Field(default_factory=list)

    @field_validator("title_zh", "title_en", mode="before")
    @classmethod
    def _clean_title(cls, value: object) -> str:
        return " ".join(str(value or "").split())

    @field_validator("facets", mode="before")
    @classmethod
    def _clean_facets(cls, value: object) -> list[object]:
        # 模型偶尔会交回字符串、单个对象或混杂项；丢掉不可解析的项，并截到上限。
        # 注意要同时放行 dict 与已构造好的 DeepDiveFacet——只认 dict 会把
        # 代码里直接传 DeepDiveFacet 的调用静默清空。
        if value is None:
            return []
        if isinstance(value, (dict, DeepDiveFacet)):
            value = [value]
        if not isinstance(value, list):
            return []
        kept: list[object] = [item for item in value if isinstance(item, (dict, DeepDiveFacet))]
        return kept[:MAX_DEEP_DIVE_FACETS]

    def title_for(self, language: str) -> str:
        if language == "en":
            return self.title_en or self.title_zh
        return self.title_zh or self.title_en

    def usable_facets(self) -> list[DeepDiveFacet]:
        """真正能上屏的分面：必须有正文；只写标题的空壳丢弃。"""
        return [facet for facet in self.facets if facet.has_body()][:MAX_DEEP_DIVE_FACETS]


class PulseCard(BaseModel):
    """一条「脉搏短讯」：事实一句 + 钩子（为什么重要 / 接下来看什么）。双语。

    在简报生成的那次 LLM 调用里产出并存进 `briefs.structured.pulses`，
    前端只读库存字段渲染，不在前端调用模型。
    诚实边界：钩子里只允许「从素材可推导的判断」与「接下来看什么」的观察点，
    不得写概率或断言未发生的事（未过评估门的推演一律不进脉搏卡）。
    """

    section_key: SectionKey = "other"
    fact_zh: str = Field(default="", max_length=280)
    fact_en: str = Field(default="", max_length=280)
    hook_zh: str = Field(default="", max_length=140)
    hook_en: str = Field(default="", max_length=140)
    source_name: str = Field(default="", max_length=120)

    @field_validator("fact_zh", "fact_en", "hook_zh", "hook_en", "source_name", mode="before")
    @classmethod
    def _clean(cls, value: object) -> str:
        return " ".join(str(value or "").split())


class BriefContent(BaseModel):
    """日报的完整内容（双语）。Markdown 由我们自己渲染，保证可复现。"""

    title_zh: str = Field(default="", max_length=200)
    title_en: str = Field(default="", max_length=200)
    overview_zh: str = Field(default="", max_length=1200)
    overview_en: str = Field(default="", max_length=1200)
    sections: list[BriefSection] = Field(default_factory=list)
    closing_zh: str = Field(default="", max_length=600)
    closing_en: str = Field(default="", max_length=600)
    # 周报用：基于统计数字的趋势观察（日报留空）
    trends_zh: list[str] = Field(default_factory=list)
    trends_en: list[str] = Field(default_factory=list)
    # 深挖：本期最值得深挖的一条事件的分面卡片（未产出时为空）
    deep_dive: DeepDive | None = None
    # 脉搏短讯：值得做成 tweet 式短讯的 3~8 条（事实 + 钩子；未产出时为空）
    pulses: list[PulseCard] = Field(default_factory=list)
    # 推演：链路式后果分析（未启用推演时为空）
    projection: ProjectionContent | None = None

    @field_validator("trends_zh", "trends_en", mode="before")
    @classmethod
    def _clean_trends(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = " ".join(str(item).split())
            if text:
                cleaned.append(text[:400])
        return cleaned[:8]

    @field_validator("sections")
    @classmethod
    def _order_sections(cls, value: list[BriefSection]) -> list[BriefSection]:
        order = {key: index for index, key in enumerate(SECTION_KEYS)}
        return sorted(value, key=lambda section: order.get(section.key, len(order)))[:5]

    def is_empty(self) -> bool:
        return not any(section.bullets_zh or section.bullets_en for section in self.sections)


class ProjectionNode(BaseModel):
    """链路里的一个节点。概率与置信度来自判官模型，措辞由模板生成。"""

    hop: int
    kind: Literal["fact", "effect", "second_order", "counter", "indicator", "horizon"]
    label_zh: str = Field(default="", max_length=120)
    label_en: str = Field(default="", max_length=160)
    statement_zh: str = Field(default="", max_length=400)
    statement_en: str = Field(default="", max_length=600)
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # 置信度不足时标记为待观察：视频与页面都不会把它当结论
    tentative: bool = False
    evidence_urls: list[str] = Field(default_factory=list)


class ProjectionChain(BaseModel):
    """一个事件的完整推演链路。"""

    document_id: int | None = None
    cluster_id: int | None = None
    source_name: str | None = None
    event_title_zh: str = Field(default="", max_length=300)
    event_title_en: str = Field(default="", max_length=300)
    nodes: list[ProjectionNode] = Field(default_factory=list)
    watch_indicators_zh: list[str] = Field(default_factory=list)
    watch_indicators_en: list[str] = Field(default_factory=list)

    def asserted_nodes(self) -> list[ProjectionNode]:
        """可以作为结论展示的节点（排除待观察）。"""
        return [node for node in self.nodes if not node.tentative]


class ProjectionContent(BaseModel):
    """一期简报的推演结果。"""

    horizon_days: int = 14
    chains: list[ProjectionChain] = Field(default_factory=list)
    # provider / model / schema 版本 / 是否通过评估门：便于事后核对数字来源
    method: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(chain.nodes for chain in self.chains)
