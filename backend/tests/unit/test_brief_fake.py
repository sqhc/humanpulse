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


async def test_fake_client_returns_usable_deep_dive() -> None:
    """fake 简报必须带可用的深挖分面，否则 CI 覆盖不到深挖卡片那条路径。"""
    client = FakeLlmClient()
    payload, _, _ = await client.complete_json(
        kind="brief", system="system", user="素材内容", model=None
    )
    content = BriefContent.model_validate(payload)
    assert content.deep_dive is not None
    facets = content.deep_dive.usable_facets()
    assert len(facets) >= 3
    # 双语分面都必须有内容，否则英文版成片会中英混排
    assert all(facet.label_zh and facet.body_zh for facet in facets)
    assert all(facet.label_en and facet.body_en for facet in facets)


async def test_fake_client_is_deterministic() -> None:
    client = FakeLlmClient()
    first, _, _ = await client.complete_json(kind="brief", system="s", user="same", model=None)
    second, _, _ = await client.complete_json(kind="brief", system="s", user="same", model=None)
    assert first == second


async def test_unknown_kind_returns_plain_object() -> None:
    client = FakeLlmClient()
    payload, _, _ = await client.complete_json(kind="other", system="s", user="u", model=None)
    assert payload["kind"] == "other"
