"""实体别名验证：调用 LLM 判定两个候选名称是否为同一个实体。"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm.base import LlmClient


@dataclass(frozen=True, slots=True)
class AliasVerification:
    """验证结果：(是否同实体, 置信度, 原因)。"""

    is_alias: bool
    confidence: float
    reason: str


async def verify_alias_pair(
    client: LlmClient,
    kind: str,
    left_name: str,
    right_name: str,
) -> AliasVerification:
    """调用 LLM 验证两个名称是否为同一实体。

    提示词重点：
    - 必须考虑跨语言（中文 $\leftrightarrow$ 英文）
    - 必须考虑简繁体
    - 必须考虑俗称与官方名称
    - 必须排除相关但不同的人/组织（例如：美国 $\leftrightarrow$ 美国政府）
    """
    system = "你是一个专家级的知识图谱对齐助手。请判定以下两个名称是否指向同一个实体。"
    user = (
        f"实体类型: {kind}\n"
        f"名称 A: {left_name}\n"
        f"名称 B: {right_name}\n\n"
        f"判定标准：\n"
        f"1. 如果两者是同一实体的不同语言写法、简繁写法或公认俗称，请判定为 'YES'。\n"
        f"2. 如果两者只是相关（例如 A 是 B 的组成部分，或 A 是 B 的领导人），请判定为 'NO'。\n"
        f"3. 如果不确定，请判定为 'NO'。\n\n"
        f"请以 JSON 格式返回结果：\n"
        f'{{ "is_alias": boolean, "confidence": float (0-1), "reason": "简短理由" }}'
    )

    payload, _, _ = await client.complete_json(
        kind="alias_verification",
        system=system,
        user=user,
    )
    # 简单解析 JSON（实际生产应使用更鲁棒的解析器）
    import json

    try:
        data = json.loads(json.dumps(payload))
        return AliasVerification(
            is_alias=bool(data.get("is_alias")),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "")),
        )
    except Exception:
        pass

    return AliasVerification(is_alias=False, confidence=0.0, reason="解析失败")
