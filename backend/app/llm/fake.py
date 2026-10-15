"""确定性假客户端：不联网，用于开发、CI 与离线演示。"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from app.llm.base import AnalyzeResult, LlmUsage
from app.llm.schema import AnalysisOut

_TAGS = (
    "conflict",
    "science",
    "labor",
    "protest",
    "policy",
    "research",
    "technology",
    "rights",
)
_REGIONS = ("asia", "europe", "africa", "americas", "oceania", "global")


def _collapse(text: str, limit: int) -> str:
    """去掉换行与多余空白后截断，保证摘要稳定且单行可读。"""
    flat = " ".join(text.split())
    return flat[:limit]


class FakeLlmClient:
    """同名同文必得同果的确定性实现，保证测试与本地演示可复现。"""

    provider = "fake"

    def __init__(self, model: str = "fake") -> None:
        self._model = model

    async def analyze(
        self,
        *,
        kind: str,
        title: str,
        text: str,
        url: str,
        model: str | None = None,
    ) -> AnalyzeResult:
        # 用内容哈希驱动所有派生结果，避免随机数或时间导致输出漂移。
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")
        score = seed % 101

        start = seed % len(_TAGS)
        count = 2 + (seed >> 8) % 2
        tags: list[str] = []
        for offset in range(count):
            tag = _TAGS[(start + offset) % len(_TAGS)]
            if tag not in tags:
                tags.append(tag)

        # 可选 1 个地区，偶尔留空，让输出更接近真实模型的多样性。
        regions: list[str] = []
        if (seed >> 16) % 4 != 0:
            regions.append(_REGIONS[(seed >> 24) % len(_REGIONS)])

        entity_name = title.strip()[:20] or "unknown"
        data = AnalysisOut(
            relevant=True,
            score=score,
            summary_zh=_collapse(text, 60),
            summary_en=_collapse(text, 60),
            tags=tags,
            regions=regions,
            rationale=f"fake 客户端依据文本哈希生成的确定性结果（kind={kind}）",
            # 传 dict 而非 EntityOut：schema 的 before 校验器只识别 str/dict。
            entities=[{"name": entity_name, "kind": "event", "salience": 0.5}],
        )
        usage = LlmUsage(
            provider=self.provider,
            model=model or self._model,
            tokens_in=max(1, len(text) // 4),
            tokens_out=max(1, len(text) // 8),
            cost_usd=Decimal(0),
        )
        return AnalyzeResult(data=data, usage=usage, repaired=False)

    async def complete_json(
        self,
        *,
        kind: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> tuple[dict[str, Any], LlmUsage, bool]:
        """确定性假简报：结构合法但不读正文，供 CI 与离线演示使用。"""
        if kind == "brief":
            payload: dict[str, Any] = {
                "title_zh": "fake 日报（离线演示）",
                "title_en": "fake daily brief (offline demo)",
                "overview_zh": "这是一份由 fake 客户端生成的确定性日报，用于 CI 与离线演示。",
                "overview_en": (
                    "Deterministic brief produced by the fake client for CI and offline demos."
                ),
                "sections": [
                    {
                        "key": "conflict",
                        "heading_zh": "冲突与安全",
                        "heading_en": "Conflict & security",
                        "bullets_zh": ["素材中存在冲突类记录（fake 客户端不读正文）。"],
                        "bullets_en": [
                            "Conflict-related records were present (contents not read)."
                        ],
                    },
                    {
                        "key": "science",
                        "heading_zh": "科技与科学",
                        "heading_en": "Science & technology",
                        "bullets_zh": ["素材中存在科技类记录（fake 客户端不读正文）。"],
                        "bullets_en": ["Science-related records were present (contents not read)."],
                    },
                ],
                "deep_dive": {
                    "title_zh": "fake 深挖事件（离线演示）",
                    "title_en": "fake deep-dive event (offline demo)",
                    "facets": [
                        {
                            "label_zh": "官方回应",
                            "label_en": "Official response",
                            "body_zh": "fake 客户端生成的确定性分面，供 CI 覆盖深挖卡片路径。",
                            "body_en": "Deterministic facet for CI coverage.",
                        },
                        {
                            "label_zh": "研究判断",
                            "label_en": "Research view",
                            "body_zh": "第二条确定性分面；fake 客户端不读正文，仅保证结构合法。",
                            "body_en": "Second deterministic facet.",
                        },
                        {
                            "label_zh": "技术手法",
                            "label_en": "Technical method",
                            "body_zh": "第三条确定性分面，用来验证「3 列 × 2 行」版式取到多张卡。",
                            "body_en": "Third deterministic facet, exercising the 3x2 card grid.",
                        },
                    ],
                },
                "closing_zh": "",
                "closing_en": "",
            }
        else:
            payload = {"kind": kind, "note": "fake 客户端只实现了 brief"}
        usage = LlmUsage(
            provider=self.provider,
            model=model or self._model,
            tokens_in=max(1, len(user) // 4),
            tokens_out=64,
            cost_usd=Decimal(0),
        )
        return payload, usage, False
