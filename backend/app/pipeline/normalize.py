"""归一化：URL 规范化、文本清洗、语言粗判、内容指纹。"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 常见的跟踪/来源参数：保留会破坏 canonical_url 的去重能力
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "yclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "referrer",
    "source",
    "from",
    "spm",
    "cmpid",
    "cid",
    "share_token",
    "__twitter_impression",
    "guccounter",
    "output",
    "at_medium",
    "at_campaign",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_HTML_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&mdash;": "—",
    "&ndash;": "–",
    "&hellip;": "…",
    "&ldquo;": "“",
    "&rdquo;": "”",
}


def strip_html(text: str) -> str:
    """去掉标签与常见实体，压平空白（不引入额外依赖）。"""
    if not text:
        return ""
    cleaned = _TAG_RE.sub(" ", text)
    for entity, char in _HTML_ENTITIES.items():
        cleaned = cleaned.replace(entity, char)
    cleaned = _WS_RE.sub(" ", cleaned)
    return _MULTI_NL_RE.sub("\n\n", cleaned).strip()


def canonicalize_url(url: str) -> str | None:
    """去掉 fragment、跟踪参数与末尾斜杠；非 http(s) 或无法解析时返回 None。"""
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query_pairs), ""))


def excerpt_of(text: str | None, limit: int = 800) -> str:
    """截断为摘要片段，按字符数控制（中英混排都适用）。"""
    if not text:
        return ""
    cleaned = strip_html(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def detect_language(text: str, fallback: str | None = None) -> str:
    """不引依赖的粗判：CJK 占比 > 20% 记 zh，否则 en；空文本用 fallback。"""
    if not text:
        return fallback or "und"
    cjk = len(_CJK_RE.findall(text))
    letters = sum(1 for ch in text if ch.isalpha() or _CJK_RE.match(ch))
    if letters == 0:
        return fallback or "und"
    if cjk / letters > 0.2:
        return "zh"
    return fallback or "en"


def content_hash(title: str, body: str) -> str:
    """标题 + 正文的稳定指纹，用于缓存同样的分析结果。"""
    digest = hashlib.sha256()
    digest.update((title or "").strip().encode("utf-8"))
    digest.update(b"\x00")
    digest.update((body or "").strip().encode("utf-8"))
    return digest.hexdigest()


def to_utc(value: datetime | None) -> datetime | None:
    """统一成 aware UTC；naive 视为 UTC。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
