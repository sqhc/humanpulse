# 诊断存档：入库标题 context 会把 Laya 的排序反转

日期：2026-10-15（同一批金标准 274 对，见 `alignment-split.json`）

## 结论

`run_alignment_eval` 早期会把「每边实体最近一次出现的报道标题」塞进判官 prompt。
同一批 60 对（正负各 30，`diag-context-60pairs.py`）实测：

| 口径 | 正样本均值 | 负样本均值 | AUC |
| --- | --- | --- | --- |
| 不带 context | 0.859 | 0.606 | **0.809** |
| 带 context（原始写法） | 0.924 | **1.178** | **0.172** |

负样本均值被抬到正样本之上——排序整个反转。换措辞、加「标题只是识别辅助、
不是判断依据」的强指令只回到 0.317 / 0.378，救不回来。

全量 274 对的两个口径（`used_context` 字段是当天稍后才加上的，所以这两份
早于该字段的产物里没有它，但文件名 `-ctx` 即带 context 口径）：

| 产物 | 口径 | Laya AUC | Jev AUC |
| --- | --- | --- | --- |
| `eval-alignment-laya.json` / `eval-alignment-jev.json` | 生产口径（不带 context） | 0.799 | 1.000 |
| `eval-alignment-laya-ctx.json` / `eval-alignment-jev-ctx.json` | 带 context（已弃用） | 0.232 | 1.000 |

所以上一轮「Laya 分类不可用（acc 0.226）」测的是提示写法的副作用，不是模型能力。
生产路径 `backend/app/pipeline/alias_adjudication.py` 的 `_as_pair` 本来就不填 context，
`16b5383` 之后评估默认口径与生产一致（`--use-context` 仅作实验开关）。

## 复现

```bash
# 生产口径（默认）与带 context 的对照
cd backend && uv run --extra judgement python -m app.cli eval-alignment --out ../.cache/eval-alignment-laya.json
cd backend && uv run --extra judgement python -m app.cli eval-alignment --use-context --out /tmp/laya-ctx.json

# 60 对诊断（需要 LOCAL Laya：make laya-serve）
cd backend && uv run --extra judgement python ../docs/evidence/diag-context-60pairs.py
```
