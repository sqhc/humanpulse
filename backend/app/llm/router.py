"""LLM 模型路由：根据任务复杂度动态选择模型。"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class RouteResult:
    model: str
    reason: str


class ModelRouter:
    """模型路由逻辑。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def route(self, prompt_kind: str, complexity: str = "medium") -> RouteResult:
        """
        路由策略：
        - 简单任务 (summarization, simple_tagging) $\rightarrow$ flash
        - 复杂任务 (projection, high_stakes_analysis) $\rightarrow$ pro
        - 默认 $\rightarrow$ flash (以成本优先)
        """
        # 1. 强制路由：某些任务必须用 pro
        if prompt_kind in ("projection", "judgement", "complex_analysis"):
            return RouteResult(self.settings.llm_model_brief, "high_complexity_task")

        # 2. 根据复杂度路由
        if complexity == "high":
            return RouteResult(self.settings.llm_model_brief, "high_complexity_requested")

        # 3. 默认路由到 flash
        return RouteResult(self.settings.llm_model_bulk, "default_cost_optimization")


# 全局路由实例
router = ModelRouter()
