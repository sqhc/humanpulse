"""LLM 入口：按配置选择具体客户端。"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.base import AnalyzeResult, LlmClient, LlmError, LlmUsage
from app.llm.client import DeepSeekClient
from app.llm.fake import FakeLlmClient
from app.llm.prompts import load_prompt
from app.llm.schema import PROMPT_VERSION, AnalysisOut

__all__ = [
    "PROMPT_VERSION",
    "AnalysisOut",
    "AnalyzeResult",
    "DeepSeekClient",
    "FakeLlmClient",
    "LlmClient",
    "LlmError",
    "LlmUsage",
    "get_llm_client",
    "load_prompt",
]


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    """按 settings.llm_provider 返回单例客户端。"""
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    if provider == "fake":
        return FakeLlmClient()
    if provider == "deepseek":
        return DeepSeekClient(settings)
    raise ValueError(f"未知的 llm_provider：{settings.llm_provider!r}（可选：deepseek、fake）")
