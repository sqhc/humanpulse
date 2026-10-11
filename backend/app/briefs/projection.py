"""推演：把今日事件变成一条带概率的因果链路。

为什么是「链路」而不是一段结论：
只问一句「会不会升级」价值有限。真正有用的是把后果拆成**可分别验证的台阶**——
事件 → 直接后果 → 二阶效应 → 反制/反馈 → 观察指标——每一跳都有独立的概率与置信度，
因此可以被分别登记、分别到期核对、分别证伪。

控制流归代码（Jev/Laya 的架构模式）：
- hop1 一次调用扇出 3 个独立问题，省一次往返；
- hop2 的问题集**取决于 hop1 的结论**（升级与降温走不同分支），这是有意的条件化；
- 概率一律来自判官模型，措辞由模板生成——不额外调用 LLM，因此零成本且可复现。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import structlog

from app.briefs.schema import ProjectionChain, ProjectionContent, ProjectionNode
from app.briefs.select import SelectedItem
from app.judgement import (
    ChoiceQuestion,
    JudgementAnswer,
    JudgementClient,
    JudgementError,
    NoulQuestion,
    Question,
    ScoreQuestion,
    get_judgement_client,
)

log = structlog.get_logger("briefs.projection")

# Laya multilingual 上下文上限 1024 token；中文大致 1 字 1 token，留出余量
DEFAULT_MAX_STATE_CHARS = 900

ESCALATION_SCALE_ZH = ("明显降温", "维持现状", "进一步升级", "失控或全面对抗")
ESCALATION_SCALE_EN = (
    "clear de-escalation",
    "roughly unchanged",
    "further escalation",
    "uncontrolled / full confrontation",
)

DOWNSTREAM_TYPES: dict[str, str] = {
    "economy": "经济与市场（价格、供应链、投资）",
    "military": "军事与安全（部队、武器、冲突）",
    "diplomacy": "外交与联盟（谈判、制裁、结盟）",
    "legal": "法律与监管（诉讼、调查、立法）",
    "technology": "科技与产业（出口管制、标准、算力）",
    "society": "社会与舆论（抗议、选举、民意）",
}

# hop2 的分支问题集：(键, 节点类型, 中文标签, 英文标签)
HOP2_ESCALATING: tuple[tuple[str, str, str, str], ...] = (
    ("direct_conflict", "second_order", "直接冲突", "Direct confrontation"),
    ("energy_shipping", "second_order", "能源与航运", "Energy and shipping"),
    ("third_party", "counter", "第三方调停", "Third-party mediation"),
)
HOP2_CALM: tuple[tuple[str, str, str, str], ...] = (
    ("negotiation", "second_order", "谈判进展", "Negotiation progress"),
    ("spillover", "second_order", "相邻领域外溢", "Spillover to adjacent domains"),
    ("third_party", "counter", "第三方调停", "Third-party mediation"),
)


def build_event_state(item: SelectedItem, *, max_chars: int = DEFAULT_MAX_STATE_CHARS) -> str:
    """把一条素材压成判官能吃的 state。

    按优先级装配：标题 > 中文摘要 > 英文摘要 > 来源 > 日期。
    超预算时先丢弃低优先级整块，最后才截断——避免为了塞进日期把摘要腰斩。
    只用已入库的摘要，不拉全文（既符合数据政策，也适配 1024 token 上限）。
    """
    blocks: list[tuple[int, str]] = [(0, f"事件：{item.title.strip()}")]
    if item.summary_zh:
        blocks.append((1, f"中文摘要：{item.summary_zh.strip()}"))
    if item.summary_en:
        blocks.append((2, f"英文摘要：{item.summary_en.strip()}"))
    if item.source_name:
        blocks.append((4, f"来源：{item.source_name}"))
    if item.published_at is not None:
        blocks.append((5, f"日期：{item.published_at:%Y-%m-%d}"))

    blocks.sort(key=lambda pair: pair[0])
    kept: list[str] = []
    used = 0
    for _, text in blocks:
        cost = len(text) + 1
        if used + cost <= max_chars:
            kept.append(text)
            used += cost
            continue
        remaining = max_chars - used - 1
        if remaining > 40:  # 太短就不值得截断，直接丢
            kept.append(text[:remaining])
        break
    return "\n".join(kept)


def build_hop1_questions(*, horizon_days: int) -> dict[str, Question]:
    """第一跳：对事件本身扇出三个独立问题（一次调用问完）。"""
    return {
        "escalation": ScoreQuestion(
            instructions=(
                f"未来 {horizon_days} 天内，该事件所涉及的对抗或冲突程度最可能如何变化？"
            ),
            criteria=ESCALATION_SCALE_ZH,
        ),
        "downstream": ChoiceQuestion(
            instructions="如果产生可见的下游后果，最可能以哪种形式出现？",
            criteria=DOWNSTREAM_TYPES,
        ),
        "indicator": NoulQuestion(
            instructions=(
                f"未来 {horizon_days} 天内是否会出现可观察的先行指标"
                "（例如官方声明、市场反应、部队调动、立法动作）？"
            )
        ),
    }


def escalation_level(answer: JudgementAnswer) -> int:
    """把 Score 答案映射到量表档位（四舍五入并对齐边界）。"""
    if answer.score is None:
        return 0
    return max(0, min(len(ESCALATION_SCALE_ZH) - 1, int(answer.score + 0.5)))


def build_hop2_questions(*, escalation: int, horizon_days: int) -> dict[str, Question]:
    """第二跳：**按第一跳结论分支**的问题集（意图路由：代码掌权）。"""
    branch = HOP2_ESCALATING if escalation >= 2 else HOP2_CALM
    mapping = {
        "direct_conflict": f"未来 {horizon_days} 天内是否会出现直接军事对抗或武装冲突？",
        "energy_shipping": "是否会明显影响能源价格、航运成本或供应链？",
        "third_party": "是否会出现有实质影响的第三方调停或斡旋？",
        "negotiation": f"未来 {horizon_days} 天内是否会出现正式谈判或协议进展？",
        "spillover": "是否会在相邻领域（贸易、科技、法律）产生外溢？",
    }
    return {key: NoulQuestion(instructions=mapping[key]) for key, _, _, _ in branch}


def build_hop3_questions(*, horizon_days: int) -> dict[str, Question]:
    """第三跳：为「到期核对」预埋一个可验证的问题。"""
    return {
        "horizon_realized": NoulQuestion(
            instructions=(f"到 {horizon_days} 天期限时，上面判断的最可能后果是否已经部分兑现？")
        ),
    }


def _label(scale_zh: Sequence[str], level: int) -> str:
    if not scale_zh:
        return ""
    return scale_zh[max(0, min(len(scale_zh) - 1, level))]


def chain_from_responses(
    item: SelectedItem,
    answers: Mapping[str, JudgementAnswer],
    *,
    horizon_days: int,
    min_confidence: float,
) -> ProjectionChain:
    """把各跳回答组装成一条链路（纯函数，便于用假判官断言）。"""
    escalation_answer = answers.get("escalation")
    level = escalation_level(escalation_answer) if escalation_answer else 0
    escalation_confidence = escalation_answer.confidence if escalation_answer else None
    branch = HOP2_ESCALATING if level >= 2 else HOP2_CALM

    nodes: list[ProjectionNode] = [
        ProjectionNode(
            hop=0,
            kind="fact",
            label_zh="事件",
            label_en="Event",
            statement_zh=item.title,
            statement_en=item.title,
            probability=1.0,
            confidence=None,
            tentative=False,
            evidence_urls=[item.url],
        )
    ]

    def tentative(confidence: float | None) -> bool:
        # 没有置信度的（Noul）不因此被降级；有置信度但不足的才标「待观察」
        return confidence is not None and confidence < min_confidence

    if escalation_answer is not None:
        label_zh = _label(ESCALATION_SCALE_ZH, level)
        label_en = _label(ESCALATION_SCALE_EN, level)
        score_text = (
            f"{escalation_answer.score:.2f}" if escalation_answer.score is not None else "-"
        )
        nodes.append(
            ProjectionNode(
                hop=1,
                kind="effect",
                label_zh="冲突烈度",
                label_en="Escalation",
                statement_zh=(
                    f"未来 {horizon_days} 天内最可能「{label_zh}」"
                    f"（量表期望分 {score_text}/3，判定概率 {escalation_answer.probability():.2f}）"
                ),
                statement_en=(
                    f"Over the next {horizon_days} days the most likely path is "
                    f"{label_en} (expected {score_text}/3, probability "
                    f"{escalation_answer.probability():.2f})"
                ),
                probability=round(escalation_answer.probability(), 4),
                confidence=escalation_confidence,
                tentative=tentative(escalation_confidence),
            )
        )

    downstream = answers.get("downstream")
    if downstream is not None and downstream.choice:
        nodes.append(
            ProjectionNode(
                hop=1,
                kind="effect",
                label_zh="下游形式",
                label_en="Downstream form",
                statement_zh=(
                    f"最可能落在「{DOWNSTREAM_TYPES.get(downstream.choice, downstream.choice)}」"
                    f"方向（概率 {downstream.probability():.2f}）"
                ),
                statement_en=(
                    f"Most likely downstream form: {downstream.choice} "
                    f"(probability {downstream.probability():.2f})"
                ),
                probability=round(downstream.probability(), 4),
                confidence=downstream.confidence,
                tentative=tentative(downstream.confidence),
            )
        )

    indicator = answers.get("indicator")
    if indicator is not None and indicator.noul is not None:
        nodes.append(
            ProjectionNode(
                hop=1,
                kind="indicator",
                label_zh="先行指标",
                label_en="Leading indicator",
                statement_zh=(
                    f"出现可观察先行指标的概率 {indicator.noul:.2f}"
                    + ("（值得持续盯）" if indicator.noul >= 0.5 else "（暂无明显信号）")
                ),
                statement_en=(
                    f"Probability of an observable leading indicator: {indicator.noul:.2f}"
                ),
                probability=round(indicator.noul, 4),
                confidence=None,
                tentative=False,
            )
        )

    for key, kind, label_zh, label_en in branch:
        answer = answers.get(key)
        if answer is None or answer.noul is None:
            continue
        nodes.append(
            ProjectionNode(
                hop=2,
                kind=kind,
                label_zh=label_zh,
                label_en=label_en,
                statement_zh=f"{label_zh}的概率 {answer.noul:.2f}",
                statement_en=f"Probability of {label_en.lower()}: {answer.noul:.2f}",
                probability=round(answer.noul, 4),
                confidence=None,
                tentative=False,
            )
        )

    horizon = answers.get("horizon_realized")
    if horizon is not None and horizon.noul is not None:
        nodes.append(
            ProjectionNode(
                hop=3,
                kind="horizon",
                label_zh="到期可兑现性",
                label_en="Realisation by horizon",
                statement_zh=(
                    f"到第 {horizon_days} 天时上述后果已部分兑现的概率 {horizon.noul:.2f}"
                ),
                statement_en=(
                    f"Probability the above has partly materialised by day "
                    f"{horizon_days}: {horizon.noul:.2f}"
                ),
                probability=round(horizon.noul, 4),
                confidence=None,
                tentative=False,
            )
        )

    indicators_zh = [
        node.statement_zh for node in nodes if node.kind == "indicator" and node.probability >= 0.5
    ]
    indicators_en = [
        node.statement_en for node in nodes if node.kind == "indicator" and node.probability >= 0.5
    ]
    return ProjectionChain(
        document_id=item.document_id,
        cluster_id=item.cluster_id,
        source_name=item.source_name,
        event_title_zh=item.title,
        event_title_en=item.title,
        nodes=nodes,
        watch_indicators_zh=indicators_zh,
        watch_indicators_en=indicators_en,
    )


async def build_chain(
    item: SelectedItem,
    *,
    client: JudgementClient,
    horizon_days: int,
    hops: int,
    min_confidence: float,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
) -> ProjectionChain:
    """跑完一条链路：hop1 扇出 → 按结论分支的 hop2 → hop3。"""
    state = build_event_state(item, max_chars=max_state_chars)
    answers: dict[str, JudgementAnswer] = {}

    hop1 = await client.ask(state, build_hop1_questions(horizon_days=horizon_days))
    answers.update(hop1.answers)

    if hops >= 2:
        level = escalation_level(answers["escalation"]) if "escalation" in answers else 0
        hop2 = await client.ask(
            state, build_hop2_questions(escalation=level, horizon_days=horizon_days)
        )
        answers.update(hop2.answers)

    if hops >= 3:
        hop3 = await client.ask(state, build_hop3_questions(horizon_days=horizon_days))
        answers.update(hop3.answers)

    return chain_from_responses(
        item,
        answers,
        horizon_days=horizon_days,
        min_confidence=min_confidence,
    )


async def generate_projection(
    items: Sequence[SelectedItem],
    *,
    horizon_days: int,
    max_events: int,
    hops: int,
    min_confidence: float,
    client: JudgementClient | None = None,
    calibrated: bool = False,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
) -> ProjectionContent | None:
    """对 Top N 事件生成推演。判官不可用时返回 None（调用方维持现状）。

    单条事件失败不影响其它事件：推演是增量能力，不能因为一次调用失败让整期简报生成不出来。
    """
    judge = client or get_judgement_client()
    if judge is None:
        return None
    selected = [item for item in items[:max_events] if item.title.strip()]
    if not selected:
        return None

    chains: list[ProjectionChain] = []
    notes: list[str] = []
    for item in selected:
        try:
            chains.append(
                await build_chain(
                    item,
                    client=judge,
                    horizon_days=horizon_days,
                    hops=hops,
                    min_confidence=min_confidence,
                    max_state_chars=max_state_chars,
                )
            )
        except JudgementError as exc:
            log.warning(
                "projection.chain_failed", document_id=item.document_id, error=str(exc)[:200]
            )
            notes.append(f"事件 {item.document_id} 推演失败：{str(exc)[:120]}")

    if not chains:
        return None
    if not calibrated:
        # 没有通过评估门之前，必须如实标注，不能让读者以为是校准过的预测
        notes.append("本推演尚未通过校准评估：概率来自模型输出，未经可靠性验证")
    return ProjectionContent(
        horizon_days=horizon_days,
        chains=chains,
        method={
            "provider": judge.provider,
            "schema_version": "v1",
            "hops": hops,
            "min_confidence": min_confidence,
            "calibrated": calibrated,
        },
        notes=notes,
    )
