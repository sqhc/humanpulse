from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.llm.base import LlmError
from app.llm.client import DeepSeekClient

_VALID = {
    "relevant": True,
    "score": 77,
    "summary_zh": "摘要",
    "summary_en": "summary",
    "tags": ["science"],
    "regions": ["asia"],
    "rationale": "理由",
    "entities": [{"name": "Acme", "kind": "org", "salience": 0.5}],
}


def _settings() -> Settings:
    return Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
    )


def _response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


async def test_invalid_then_valid_json_is_repaired_once() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _response("这不是 JSON")
        return _response(json.dumps(_VALID))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = DeepSeekClient(_settings(), client=http_client)
        result = await client.analyze(kind="news", title="t", text="body", url="u")

    assert result.repaired is True
    assert result.data.score == 77
    assert calls["n"] == 2
    assert result.usage.provider == "deepseek"


async def test_two_invalid_json_outputs_raise_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response("仍然不是 JSON")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = DeepSeekClient(_settings(), client=http_client)
        with pytest.raises(LlmError):
            await client.analyze(kind="report", title="t", text="body", url="u")


async def test_missing_api_key_raises_llm_error() -> None:
    client = DeepSeekClient(Settings(deepseek_api_key=""))
    with pytest.raises(LlmError):
        await client.analyze(kind="news", title="t", text="body", url="u")
