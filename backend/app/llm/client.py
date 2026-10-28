"""DeepSeek Chat Completions 客户端：结构化输出 + 一次修复重试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.llm.base import AnalyzeResult, LlmError, LlmUsage
from app.llm.pricing import TokenBundle, cost_usd
from app.llm.prompts import load_prompt
from app.llm.router import router
from app.llm.schema import AnalysisOut


class _OutputError(RuntimeError):
    """内部异常：模型输出无法解析，用于触发一次修复重试。

    故意不继承 LlmError，避免修复前的失败被当成最终错误直接抛出。
    """


def _to_int(value: object) -> int:
    """把 OpenAI 兼容响应里的 token 计数安全地转成 int。"""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _truncate(value: str, limit: int = 300) -> str:
    """截断长文本，避免把整段模型输出原样写进日志或异常信息。"""
    return value if len(value) <= limit else value[:limit] + "…"


def _brief_validation_error(exc: ValidationError) -> str:
    """把 pydantic 校验错误压缩成一行中文可读摘要。"""
    parts: list[str] = []
    for error in exc.errors()[:3]:
        loc = ".".join(str(item) for item in error["loc"])
        parts.append(f"{loc}: {error['msg']}")
    return "; ".join(parts) or "未知校验错误"


class DeepSeekClient:
    """基于 DeepSeek /chat/completions 的客户端（逐条分析 + 通用 JSON 调用）。"""

    provider = "deepseek"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # api key 为空不在构造时抛错，方便健康检查等场景先实例化；调用时再报错。
        self._api_key = self._settings.deepseek_api_key.strip()
        self._base_url = self._settings.deepseek_base_url.rstrip("/")
        # 注入的 client 由调用方负责关闭（测试用 MockTransport）；未注入时按需创建。
        self._client = client

    async def analyze(
        self,
        *,
        kind: str,
        title: str,
        text: str,
        url: str,
        model: str | None = None,
    ) -> AnalyzeResult:
        self._require_key()
        # 动态路由：优先使用 router 决定模型
        chosen_model = model or router.route(kind).model
        # 模板用 str.format 填充，故 md 中除 {title}/{url}/{text} 外的花括号需双写。
        prompt = load_prompt(kind).format(title=title, url=url, text=text)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"标题：{title}\n链接：{url}\n正文：\n{text}"},
        ]
        payload, usage, repaired = await self._call_with_repair(
            messages, chosen_model, self._parse_analysis
        )
        return AnalyzeResult(
            data=AnalysisOut.model_validate(payload), usage=usage, repaired=repaired
        )

    async def complete_json(
        self,
        *,
        kind: str,
        system: str,
        user: str,
        model: str | None = None,
    ) -> tuple[dict[str, Any], LlmUsage, bool]:
        """通用 JSON 调用：简报组稿等非逐条分析场景用（默认走更强的 brief 模型）。"""
        self._require_key()
        # 动态路由
        chosen_model = model or router.route(kind).model
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self._call_with_repair(messages, chosen_model, self._parse_object)

    def _require_key(self) -> None:
        if not self._api_key:
            raise LlmError(
                "未配置 DEEPSEEK_API_KEY，无法调用 deepseek；请设置后重试或改用 fake provider"
            )

    async def _call_with_repair(
        self,
        messages: list[dict[str, str]],
        model: str,
        parse: Callable[[str], dict[str, Any]],
    ) -> tuple[dict[str, Any], LlmUsage, bool]:
        """调用一次；解析失败时把错误摘要回灌，再试一次。"""
        bundle = TokenBundle()
        raw_output = ""
        first_reason = ""
        try:
            raw_output, call_usage = await self._chat(messages, model)
            bundle = bundle + call_usage
            payload = parse(raw_output)
        except _OutputError as exc:
            first_reason = str(exc)
        except LlmError as exc:
            first_reason = str(exc)
        else:
            return payload, self._usage(model, bundle), False

        repair_messages: list[dict[str, str]] = [
            messages[0],
            {
                "role": "user",
                "content": (
                    f"{messages[1]['content']}\n\n"
                    "上一次回复无法通过 JSON 校验。\n"
                    f"错误摘要：{_truncate(first_reason)}\n"
                    "请严格只输出一个 JSON 对象，不要 markdown 代码块，不要解释。\n"
                    f"上一次回复内容：\n{_truncate(raw_output, 2000)}"
                ),
            },
        ]
        try:
            raw_output, call_usage = await self._chat(repair_messages, model)
            bundle = bundle + call_usage
            payload = parse(raw_output)
        except (_OutputError, LlmError) as exc:
            raise LlmError(
                f"deepseek 两次调用均失败：首次原因={_truncate(first_reason)}；"
                f"修复后原因={_truncate(str(exc))}"
            ) from exc
        return payload, self._usage(model, bundle), True

    async def _chat(self, messages: list[dict[str, str]], model: str) -> tuple[str, TokenBundle]:
        """发一次请求并取回 (content, token 用量)。

        缓存命中/未命中分开取：DeepSeek 的缓存命中价只有未命中的 1/50，
        合并计费会把成本算高一个数量级。
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        url = self._base_url + "/chat/completions"
        headers = {"Authorization": "Bearer " + self._api_key}
        try:
            response = await self._post(url, payload, headers)
        except httpx.HTTPError as exc:
            # 只暴露异常类型，避免把可能含 key 的请求细节带进对外信息。
            raise LlmError(f"请求 deepseek 失败：{type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise LlmError(
                f"deepseek 返回 HTTP {response.status_code}：{_truncate(response.text, 200)}"
            )
        try:
            body: Any = response.json()
        except ValueError as exc:
            raise LlmError("deepseek 响应不是合法 JSON") from exc
        try:
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            prompt_tokens = _to_int(usage.get("prompt_tokens"))
            cache_hit = _to_int(usage.get("prompt_cache_hit_tokens"))
            raw_miss = usage.get("prompt_cache_miss_tokens")
            cache_miss = (
                _to_int(raw_miss) if raw_miss is not None else max(prompt_tokens - cache_hit, 0)
            )
            bundle = TokenBundle(
                cache_hit=cache_hit,
                cache_miss=cache_miss,
                output=_to_int(usage.get("completion_tokens")),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("deepseek 响应缺少 choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LlmError("deepseek 返回了空的 message.content")
        return content, bundle

    async def _post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(url, json=payload, headers=headers)
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            return await client.post(url, json=payload, headers=headers)

    def _parse_object(self, content: str) -> dict[str, Any]:
        """严格解析模型输出：只接受裸 JSON 对象，markdown 代码块等一律视为失败。"""
        try:
            payload = json.loads(content.strip())
        except json.JSONDecodeError as exc:
            raise _OutputError(f"输出不是合法 JSON（{exc.msg}）") from exc
        if not isinstance(payload, dict):
            raise _OutputError("输出 JSON 顶层必须是对象")
        return payload

    def _parse_analysis(self, content: str) -> dict[str, Any]:
        payload = self._parse_object(content)
        try:
            return AnalysisOut.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise _OutputError(f"输出字段校验失败：{_brief_validation_error(exc)}") from exc

    def _usage(self, model: str, bundle: TokenBundle) -> LlmUsage:
        return LlmUsage(
            provider=self.provider,
            model=model,
            tokens_in=bundle.tokens_in,
            tokens_out=bundle.output,
            cache_hit_tokens=bundle.cache_hit,
            cache_miss_tokens=bundle.cache_miss,
            cost_usd=cost_usd(
                model,
                cache_hit_tokens=bundle.cache_hit,
                cache_miss_tokens=bundle.cache_miss,
                output_tokens=bundle.output,
            ),
        )
