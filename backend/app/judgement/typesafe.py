"""通过 TypeSafe SDK 调判官：云端 Jev 与本地 Laya 只差一个 base_url。

本地 Laya 的 serve.py 暴露的是 Jev 兼容路由（POST /v1/systemone），
所以这里不需要为本地/云端写两套代码——这正是选择该 SDK 的原因。
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping
from typing import Any

from app.config import Settings, get_settings
from app.judgement.base import (
    ChoiceQuestion,
    JudgementAnswer,
    JudgementError,
    JudgementResponse,
    Question,
    ScoreQuestion,
)

_VALID_KINDS = ("choice", "score", "noul")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def answer_from_raw(key: str, raw: Any) -> JudgementAnswer:
    """把 SDK 的 answer 对象转成我们的中性结构。

    用鸭子类型而不是 SDK 的类：测试可以拿一个简单的假对象直接验证转换逻辑，
    CI 也不需要安装 typesafe-sdk。
    """
    kind = str(getattr(raw, "type", "") or "")
    if kind not in _VALID_KINDS:
        kind = "noul"
    raw_probs = getattr(raw, "probabilities", None) or {}
    probabilities: dict[str, float] = {}
    if isinstance(raw_probs, Mapping):
        for option, weight in raw_probs.items():
            value = _as_float(weight)
            if value is not None:
                probabilities[str(option)] = value
    return JudgementAnswer(
        key=key,
        kind=kind,  # type: ignore[arg-type]
        choice=getattr(raw, "choice", None),
        score=_as_float(getattr(raw, "score", None)),
        noul=_as_float(getattr(raw, "noul", None)),
        probabilities=probabilities,
        confidence=_as_float(getattr(raw, "confidence", None)),
    )


class TypeSafeJudgementClient:
    """Jev / Laya 判官客户端（异步）。"""

    def __init__(self, settings: Settings | None = None, *, provider: str = "laya") -> None:
        self._settings = settings or get_settings()
        self.provider = provider
        self._client: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is None:
                try:
                    module = importlib.import_module("typesafe_sdk")
                except ImportError as exc:  # pragma: no cover - 依赖缺失时的路径
                    raise JudgementError(
                        "未安装 typesafe-sdk：请先 uv sync --extra judgement"
                    ) from exc
                self._client = module.AsyncTypeSafeClient(
                    # 本地 Laya 的 serve.py 不校验 Key，但 SDK 要求非空
                    api_key=self._settings.judgement_api_key or "local-laya",
                    base_url=self._settings.judgement_base_url,
                    timeout=self._settings.judgement_timeout_seconds,
                )
        return self._client

    def _build_sdk_questions(
        self, module: Any, questions: Mapping[str, Question]
    ) -> dict[str, Any]:
        built: dict[str, Any] = {}
        for key, question in questions.items():
            if isinstance(question, ChoiceQuestion):
                built[key] = module.Choice(
                    instructions=question.instructions, criteria=dict(question.criteria)
                )
            elif isinstance(question, ScoreQuestion):
                built[key] = module.Score(
                    instructions=question.instructions, criteria=list(question.criteria)
                )
            else:
                built[key] = module.Noul(
                    instructions=question.instructions, criteria=question.criteria
                )
        return built

    async def ask(
        self,
        state: str,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
    ) -> JudgementResponse:
        if not questions:
            raise JudgementError("没有要问的问题")
        client = await self._ensure_client()
        module = importlib.import_module("typesafe_sdk")
        try:
            raw = await client.system_one(
                state,
                self._build_sdk_questions(module, questions),
                model=model or self._settings.judgement_model,
            )
        except Exception as exc:
            # 判官不可用时必须抛错而不是返回编造的概率：调用方据此降级（不出推演）
            raise JudgementError(f"判官调用失败（{self.provider}）：{exc}") from exc

        answers: dict[str, JudgementAnswer] = {}
        for key, answer in (getattr(raw, "answers", None) or {}).items():
            answers[str(key)] = answer_from_raw(str(key), answer)
        missing = set(questions) - set(answers)
        if missing:
            raise JudgementError(f"判官没有回答全部问题，缺失：{sorted(missing)}")
        usage = getattr(raw, "usage", None)
        tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage is not None else 0
        return JudgementResponse(
            answers=answers,
            model=str(getattr(raw, "model", "") or (model or self._settings.judgement_model)),
            input_tokens=tokens,
        )
