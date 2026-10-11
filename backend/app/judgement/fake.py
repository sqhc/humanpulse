"""确定性假判官：CI 与无模型环境下跑通全链路。

概率由 state + 问题键的稳定哈希产生，因此同一输入永远得到同一输出——
测试可以断言具体数值，不需要网络，也不需要 2.2GB 权重。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from app.judgement.base import (
    ChoiceQuestion,
    JudgementAnswer,
    JudgementResponse,
    NoulQuestion,
    Question,
)


def _unit(*parts: str) -> float:
    """把任意字符串映射到 [0,1)，跨进程稳定（不用内置 hash）。"""
    digest = hashlib.blake2b("|".join(parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(1 << 64)


class FakeJudgementClient:
    provider = "fake"

    async def ask(
        self,
        state: str,
        questions: Mapping[str, Question],
        *,
        model: str | None = None,
    ) -> JudgementResponse:
        prefix = state[:200]
        answers: dict[str, JudgementAnswer] = {}
        for key, question in questions.items():
            if isinstance(question, NoulQuestion):
                answers[key] = JudgementAnswer(
                    key=key, kind="noul", noul=round(_unit(key, prefix), 4)
                )
                continue
            if isinstance(question, ChoiceQuestion):
                options = list(question.criteria)
                raw = {option: _unit(key, option, prefix) for option in options} if options else {}
                total = sum(raw.values())
                weights = (
                    {option: value / total for option, value in raw.items()} if total > 0 else {}
                )
                best = max(weights, key=lambda option: weights[option]) if weights else None
                answers[key] = JudgementAnswer(
                    key=key,
                    kind="choice",
                    choice=best,
                    probabilities={option: round(w, 4) for option, w in weights.items()},
                    confidence=round(_unit("conf", key, prefix), 4),
                )
                continue
            # ScoreQuestion：在量表上构造一个单峰分布
            levels = list(question.criteria)
            center = _unit(key, prefix) * max(len(levels) - 1, 1)
            weights = {
                str(index): round(max(0.0001, 1.0 - abs(index - center) / max(len(levels), 1)), 4)
                for index in range(len(levels))
            }
            total = sum(weights.values()) or 1.0
            probs = {index: round(weight / total, 4) for index, weight in weights.items()}
            expected = sum(int(index) * weight for index, weight in probs.items())
            answers[key] = JudgementAnswer(
                key=key,
                kind="score",
                score=round(expected, 4),
                probabilities=probs,
                confidence=round(_unit("conf", key, prefix), 4),
            )
        return JudgementResponse(answers=answers, model="fake-judgement", input_tokens=0)
