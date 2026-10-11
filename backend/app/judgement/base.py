"""判官客户端契约：类型化决策（choice / score / noul），而不是自由文本。

为什么它是独立于 LlmClient 的第二类客户端：
判官模型**不生成文本**，它只回答「在给定候选项上怎么打分」。推演里的概率必须来自它，
措辞可以来自 LLM 或模板。把两者混成一个 Protocol 会让「概率是不是模型真给的」变得不可查。

三种原语（沿用 Jev / Laya 的约定）：
- Choice：在命名选项里选一个，返回 choice + probabilities + confidence
- Score ：在有序量表上打分，返回期望分 + probabilities + confidence
- Noul  ：是非题，返回「是」的概率（本身就是概率，因此没有 confidence 字段）
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

QuestionKind = Literal["choice", "score", "noul"]


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    """从命名选项中选一个。criteria 是「选项 -> 判定说明」，两边都要给模型。"""

    instructions: str
    criteria: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ScoreQuestion:
    """按有序量表打分；量表顺序即大小顺序（低 -> 高）。"""

    instructions: str
    criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NoulQuestion:
    """是非题；criteria 可选，用来补充「是/否」的边界。"""

    instructions: str
    criteria: str | None = None


Question = ChoiceQuestion | ScoreQuestion | NoulQuestion


@dataclass(slots=True)
class JudgementAnswer:
    """单个问题的回答。三种原语各用其中一部分字段。"""

    key: str
    kind: QuestionKind
    choice: str | None = None
    score: float | None = None
    noul: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None

    def probability(self) -> float:
        """统一成一个 0-1 的「这件事有多可能」的口径，便于门控与登记预测。

        - noul：本身就是概率
        - choice：选中项的预测概率（不是 confidence）
        - score：落在量表后半区间的概率质量之和
        """
        if self.kind == "noul":
            return float(self.noul or 0.0)
        if self.kind == "choice":
            if self.choice and self.choice in self.probabilities:
                return float(self.probabilities[self.choice])
            return float(max(self.probabilities.values(), default=0.0))
        if not self.probabilities:
            return 0.0
        numeric = [(int(k), float(v)) for k, v in self.probabilities.items() if str(k).isdigit()]
        if not numeric:
            return 0.0
        top = max(value for value, _ in numeric)
        half = (top + 1) / 2
        return float(sum(weight for value, weight in numeric if value >= half))


@dataclass(slots=True)
class JudgementResponse:
    answers: dict[str, JudgementAnswer]
    model: str
    input_tokens: int = 0


class JudgementClient(Protocol):
    provider: str

    async def ask(
        self,
        state: str,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
    ) -> JudgementResponse:
        """一次调用回答多个问题（推测性扇出：代码只取当前分支需要的那几个）。"""
        ...


class JudgementError(RuntimeError):
    """判官调用失败：连不上、鉴权失败、返回结构不符合预期。"""
