from __future__ import annotations

from app.llm.base import AnalyzeResult
from app.llm.fake import FakeLlmClient


async def test_fake_client_is_deterministic() -> None:
    client = FakeLlmClient()
    kwargs = {
        "kind": "news",
        "title": "某地冲突升级",
        "text": "这是一段用于测试的正文，包含 mixed ASCII words 与数字 123。",
        "url": "https://example.com/a",
    }
    first = await client.analyze(**kwargs)
    second = await client.analyze(**kwargs)

    assert isinstance(first, AnalyzeResult)
    assert first.data.score == second.data.score
    assert first.data.summary_zh == second.data.summary_zh
    assert first.data.tags == second.data.tags
    assert first.data.entities[0].name == second.data.entities[0].name


async def test_fake_client_reports_fake_provider() -> None:
    client = FakeLlmClient()
    result = await client.analyze(kind="discussion", title="t", text="body text", url="u")
    assert result.usage.provider == "fake"
    assert result.repaired is False
