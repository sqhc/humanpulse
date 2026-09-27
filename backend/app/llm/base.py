"""LLM 客户端契约与用量记录。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.llm.schema import AnalysisOut


@dataclass(slots=True)
class LlmUsage:
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal(0)

    def __add__(self, other: LlmUsage) -> LlmUsage:
        if (self.provider, self.model) != (other.provider, other.model):
            return self
        return LlmUsage(
            provider=self.provider,
            model=self.model,
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            cost_usd=self.cost_usd + other.cost_usd,
        )


@dataclass(slots=True)
class AnalyzeResult:
    data: AnalysisOut
    usage: LlmUsage
    repaired: bool = False


class LlmClient(Protocol):
    provider: str

    async def analyze(
        self, *, kind: str, title: str, text: str, url: str, model: str | None = None
    ) -> AnalyzeResult:
        """把一条内容变成结构化分析；失败应抛 LlmError 而不是返回半成品。"""
        ...


class LlmError(RuntimeError):
    """LLM 调用或输出校验失败。"""
