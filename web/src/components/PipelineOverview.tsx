import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";

interface PipelineOverviewProps {
  lang: Lang;
  t: Messages;
}

/** 5 阶段语义配色（复用视频卡片 3×2 体系：conflict=玫红 / labor=琥珀 / science=青蓝）。 */
const STAGE_COLORS: Record<string, string> = {
  fetch: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  enrich: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  store: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  judge: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  output: "bg-teal-500/15 text-teal-300 ring-teal-500/30",
};

/** 判官概率门禁常量（config 侧 projection_enabled=false，非文档字段）。 */
const JUDGE_GATE = {
  skill: -0.362,
  ece: 0.193,
  auc: 0.528,
  minSkill: 0.05,
  maxEce: 0.15,
};

interface Stage {
  key: string;
  label: string;
  detail: string;
}

export function PipelineOverview({ lang, t }: PipelineOverviewProps) {
  const api = useMemo(() => createApiClient(), []);
  const zh = lang === "zh";

  const sources = useQuery({
    queryKey: ["pipeline", "sources"],
    queryFn: ({ signal }) => api.listSources({ signal }),
  });

  const documents = useQuery({
    queryKey: ["pipeline", "documents"],
    queryFn: ({ signal }) =>
      api.listDocuments({ limit: 500 }, { signal }),
  });

  const brief = useQuery({
    queryKey: ["pipeline", "brief", "weekly"],
    queryFn: ({ signal }) => api.getLatestBrief("weekly", { signal }),
  });

  const statusCounts = useMemo(() => {
    const items = documents.data?.items ?? [];
    const counts: Record<string, number> = {};
    for (const doc of items) {
      counts[doc.status] = (counts[doc.status] ?? 0) + 1;
    }
    return counts;
  }, [documents.data]);

  const sourceCount = sources.data?.length ?? 0;
  const enrichedCount = statusCounts["enriched"] ?? 0;
  const totalDocs = documents.data?.total_returned ?? 0;
  const briefTitle = brief.data?.title ?? "";
  const briefItemCount = brief.data?.item_count ?? 0;

  const stages: Stage[] = [
    {
      key: "fetch",
      label: zh ? "采集" : "Fetch",
      detail: zh
        ? `${sourceCount} 源 · ${totalDocs} 条`
        : `${sourceCount} sources · ${totalDocs} items`,
    },
    {
      key: "enrich",
      label: zh ? "富化" : "Enrich",
      detail: zh ? `${enrichedCount} 条已富化` : `${enrichedCount} enriched`,
    },
    {
      key: "store",
      label: zh ? "入库" : "Store",
      detail: "PostgreSQL + pgvector",
    },
    {
      key: "judge",
      label: zh ? "判官" : "Judge",
      detail: zh
        ? `概率未过门 · AUC ${JUDGE_GATE.auc}`
        : `Gate failed · AUC ${JUDGE_GATE.auc}`,
    },
    {
      key: "output",
      label: zh ? "输出" : "Output",
      detail: briefTitle
        ? (zh
            ? `${briefTitle} · ${briefItemCount} 条`
            : `${briefTitle} · ${briefItemCount} items`)
        : (zh ? "简报 · 视频" : "Brief · Video"),
    },
  ];

  const loading = sources.isPending || documents.isPending || brief.isPending;

  return (
    <section
      className="rounded-xl border border-line bg-surface-muted/60 p-5"
      data-testid="pipeline-overview"
    >
      <h2 className="text-sm font-medium text-ink-muted">
        {zh ? "流水线概览" : "Pipeline Overview"}
      </h2>

      {/* 5 阶段横条 */}
      <div className="mt-3 flex flex-wrap items-center gap-1">
        {stages.map((stage, index) => (
          <div key={stage.key} className="flex items-center gap-1">
            <span
              className={`inline-flex rounded-md px-2.5 py-1 text-xs font-medium ring-1 ${
                STAGE_COLORS[stage.key] ?? ""
              }`}
            >
              {stage.label}
            </span>
            {index < stages.length - 1 && (
              <span className="text-ink-muted/40" aria-hidden="true">
                →
              </span>
            )}
          </div>
        ))}
      </div>

      {/* 阶段详情网格 */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {stages.map((stage) => (
          <div
            key={stage.key}
            className="rounded-lg border border-line/50 bg-surface/40 p-2"
          >
            <p className="text-[11px] font-medium text-ink-muted">
              {stage.label}
            </p>
            <p className="mt-0.5 text-xs text-ink/80">{stage.detail}</p>
          </div>
        ))}
      </div>

      {/* 判官门禁提示卡片 */}
      <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
        <div className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full bg-rose-400"
            aria-hidden="true"
          />
          <p className="text-xs font-medium text-rose-300">
            {zh ? "判官门禁：未过" : "Judge gate: not passed"}
          </p>
        </div>
        <p className="mt-1 text-xs text-ink-muted">
          {zh
            ? `Brier 技能分 ${JUDGE_GATE.skill} · ECE ${JUDGE_GATE.ece} · AUC ${JUDGE_GATE.auc}`
            : `Brier skill ${JUDGE_GATE.skill} · ECE ${JUDGE_GATE.ece} · AUC ${JUDGE_GATE.auc}`}
          {" "}
          {zh
            ? `（门槛 skill >${JUDGE_GATE.minSkill} 且 ECE <${JUDGE_GATE.maxEce}）`
            : `(threshold: skill >${JUDGE_GATE.minSkill} & ECE <${JUDGE_GATE.maxEce})`}
        </p>
        <p className="mt-1 text-xs text-rose-300/80">
          {zh
            ? "projection_enabled=false · 推演强制标注「未经校准」"
            : "projection_enabled=false · projections labeled uncalibrated"}
        </p>
      </div>

      {loading ? (
        <p className="mt-2 text-xs text-ink-muted">{t.loading}</p>
      ) : null}
    </section>
  );
}