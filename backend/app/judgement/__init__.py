"""判官入口：按配置选择 Jev / 本地 Laya / 假实现。"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.judgement.base import (
    ChoiceQuestion,
    JudgementAnswer,
    JudgementClient,
    JudgementError,
    JudgementResponse,
    NoulQuestion,
    Question,
    ScoreQuestion,
)
from app.judgement.fake import FakeJudgementClient
from app.judgement.typesafe import TypeSafeJudgementClient

__all__ = [
    "ChoiceQuestion",
    "FakeJudgementClient",
    "JudgementAnswer",
    "JudgementClient",
    "JudgementError",
    "JudgementResponse",
    "NoulQuestion",
    "Question",
    "ScoreQuestion",
    "TypeSafeJudgementClient",
    "get_judgement_client",
]


@lru_cache(maxsize=1)
def get_judgement_client() -> JudgementClient | None:
    """按 settings.judgement_provider 返回单例；none 返回 None（表示不做推演）。"""
    settings = get_settings()
    provider = settings.judgement_provider.strip().lower()
    if provider in {"none", ""}:
        return None
    if provider == "fake":
        return FakeJudgementClient()
    if provider in {"laya", "jev"}:
        return TypeSafeJudgementClient(settings, provider=provider)
    raise JudgementError(
        f"未知的 judgement_provider：{settings.judgement_provider!r}（可选：none、fake、laya、jev）"
    )
