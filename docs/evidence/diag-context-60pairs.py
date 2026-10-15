"""临时诊断 2：context（入库标题）是否把 Laya 的排序搞反。

同 60 对，分别在「带 context」（生产口径）与「不带 context」下问一次，各算 AUC。
跑完即弃（.cache 已 gitignore）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.eval.alignment import (  # noqa: E402
    Pair,
    _contexts,
    alignment_question,
    build_prompt,
    pairs_from_alias_groups,
    roc_auc,
)
from app.db import get_sessionmaker  # noqa: E402
from app.judgement import get_judgement_client  # noqa: E402
from app.pipeline.aliases import load_alias_groups  # noqa: E402

SAMPLE = 60


async def ask_all(judge, question, pairs):
    scored = []
    for pair in pairs:
        response = await judge.ask(build_prompt(pair), {"same_entity": question})
        answer = response.answers.get("same_entity")
        scored.append((pair, float(answer.score or 0.0) if answer else 0.0))
    return scored


def summaries(scored):
    pos = [s for p, s in scored if p.label]
    neg = [s for p, s in scored if not p.label]
    with_ctx = [s for p, s in scored if p.left_context or p.right_context]
    return (
        f"n={len(scored)} pos_mean={sum(pos) / len(pos):.3f} neg_mean={sum(neg) / len(neg):.3f} "
        f"auc={roc_auc(scored):.3f} 有context的对数={len(with_ctx)}"
    )


async def main() -> None:
    judge = get_judgement_client()
    pairs = pairs_from_alias_groups(load_alias_groups())
    positives = [p for p in pairs if p.label][: SAMPLE // 2]
    negatives = [p for p in pairs if not p.label][: SAMPLE // 2]
    plain = positives + negatives

    names = sorted({p.left for p in plain} | {p.right for p in plain})
    factory = get_sessionmaker()
    async with factory() as session:
        contexts = await _contexts(session, names)
    enriched = [
        Pair(
            left=p.left,
            right=p.right,
            label=p.label,
            left_context=contexts.get(p.left, ""),
            right_context=contexts.get(p.right, ""),
        )
        for p in plain
    ]

    question = alignment_question()
    without = await ask_all(judge, question, plain)
    with_ctx = await ask_all(judge, question, enriched)
    print("不带 context:", summaries(without))
    print("带   context:", summaries(with_ctx))


asyncio.run(main())
