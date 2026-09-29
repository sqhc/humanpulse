"""SSE 帧格式：客户端按 event/data/空行解析，格式错一个字符前端就收不到。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.api.v1.stream import document_payload, sse_frame
from app.models.analysis import Analysis
from app.models.document import Document


def test_sse_frame_shape() -> None:
    frame = sse_frame("document", {"id": 1, "title": "中文标题"})
    assert frame.startswith("event: document\n")
    assert frame.endswith("\n\n")
    body = frame.split("data: ", 1)[1].strip()
    assert json.loads(body) == {"id": 1, "title": "中文标题"}
    # 中文不能被转义成 \uXXXX，否则前端拿到的是乱码可读性差的字符串
    assert "中文标题" in frame


def test_document_payload_serialises_dates_and_tags() -> None:
    document = Document(
        id=7,
        title="Ceasefire talks resume",
        url="https://example.test/a",
        canonical_url="https://example.test/a",
        kind="news",
        status="enriched",
        language="en",
        published_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 9, 27, 12, 5, tzinfo=UTC),
    )
    analysis = Analysis(
        id=1,
        document_id=7,
        prompt_version="v1",
        provider="deepseek",
        model="deepseek-flash",
        score=80,
        summary_zh="中文摘要",
        summary_en="English summary",
        tags=["conflict"],
        regions=["asia"],
    )
    payload = document_payload(document, analysis, 3, "Al Jazeera")
    assert payload["id"] == 7
    assert payload["score"] == 80
    assert payload["tags"] == ["conflict"]
    assert payload["cluster_id"] == 3
    assert payload["source_name"] == "Al Jazeera"
    assert payload["published_at"] == "2026-09-27T12:00:00+00:00"


def test_document_payload_tolerates_missing_analysis() -> None:
    document = Document(
        id=8,
        title="No analysis yet",
        url="https://example.test/b",
        canonical_url="https://example.test/b",
        kind="news",
        status="pending",
        fetched_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    payload = document_payload(document, None, None, None)
    assert payload["score"] is None
    assert payload["tags"] == []
    assert payload["summary_zh"] is None
    assert payload["published_at"] is None
