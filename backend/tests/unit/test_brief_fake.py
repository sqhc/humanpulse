"""fake 客户端要能产出合法简报结构，CI 才能在不联网的情况下验证整条链路。"""

from __future__ import annotations

from app.briefs.schema import BriefContent
from app.llm.fake import FakeLlmClient


async def test_fake_client_returns_valid_brief() -> None:
    client = FakeLlmClient()
    payload, usage, repaired = await client.complete_json(
        kind="brief", system="system", user="素材内容", model=None
    )
    content = BriefContent.model_validate(payload)
    assert content.title_zh
    assert content.sections
    assert repaired is False
    assert usage.provider == "fake"
    assert usage.tokens_in > 0


async def test_fake_client_is_deterministic() -> None:
    client = FakeLlmClient()
    first, _, _ = await client.complete_json(kind="brief", system="s", user="same", model=None)
    second, _, _ = await client.complete_json(kind="brief", system="s", user="same", model=None)
    assert first == second


async def test_unknown_kind_returns_plain_object() -> None:
    client = FakeLlmClient()
    payload, _, _ = await client.complete_json(kind="other", system="s", user="u", model=None)
    assert payload["kind"] == "other"
