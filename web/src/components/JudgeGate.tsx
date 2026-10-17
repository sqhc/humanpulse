import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";

/** 判官概率门禁常量（config 侧 projection_enabled=false；复测结论，勿改口径）。 */
const JUDGE_GATE = {
  skill: -0.362,
  ece: 0.193,
  auc: 0.528,
  minSkill: 0.05,
  maxEce: 0.15,
};

const STATUS_LABEL: Record<string, { zh: string; en: string }> = {
  open: { zh: "待核对", en: "open" },
  hit: { zh: "已兑现", en: "hit" },
  missed: { zh: "未兑现", en: "missed" },
  expired: { zh: "已过期", en: "expired" },
  unresolved: { zh: "无证据", en: "unresolved" },
};

function fmtDate(iso: string, zh: boolean): string {
  return new Date(iso).toLocaleDateString(zh ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function JudgeGate({ lang, t }: { lang: Lang; t: Messages }) {
  const api = useMemo(() => createApiClient(), []);
  const zh = lang === "zh";

  const calibration = useQuery({
    queryKey: ["judge", "calibration"],
    queryFn: ({ signal }) => api.getCalibration(undefined, { signal }),
  });
  const predictions = useQuery({
    queryKey: ["judge", "predictions"],
    queryFn: ({ signal }) => api.listPredictions({ limit: 20 }, { signal }),
  });

  const loading = calibration.isPending || predictions.isPending;
  const cal = calibration.data;
  const items = predictions.data?.items ?? [];
  const reliability = cal?.reliability ?? [];
  const maxReliabilityCount = reliability.reduce(
    (max, bucket) => Math.max(max, bucket.count),
    0,
  );

  return (
    <section className="space-y-5">
      {/* 门禁状态卡 */}
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-5">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-400" aria-hidden="true" />
          <h2 className="text-base font-semibold text-rose-300">
            {zh ? "判官概率门禁：未通过" : "Judge probability gate: not passed"}
          </h2>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <div>
            <dt className="text-[11px] text-ink-muted">Brier skill</dt>
            <dd className="text-sm font-mono text-ink">{JUDGE_GATE.skill}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-muted">ECE</dt>
            <dd className="text-sm font-mono text-ink">{JUDGE_GATE.ece}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-muted">AUC</dt>
            <dd className="text-sm font-mono text-ink">{JUDGE_GATE.auc}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-muted">{zh ? "门槛 skill" : "gate skill"}</dt>
            <dd className="text-sm font-mono text-ink-muted">
              &gt;{JUDGE_GATE.minSkill}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-muted">{zh ? "门槛 ECE" : "gate ECE"}</dt>
            <dd className="text-sm font-mono text-ink-muted">&lt;{JUDGE_GATE.maxEce}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-rose-300/80">
          {zh
            ? "AUC 0.528 ≈ 随机（本质不可用）· 概率不可发布 · projection_enabled=false · 推演一律标注「未经校准」"
            : "AUC 0.528 ≈ random (no discriminative power) · not publishable · projection_enabled=false · all projections labeled uncalibrated"}
        </p>
      </div>

      {/* 校准汇总 */}
      <div className="rounded-xl border border-line bg-surface-muted/40 p-5">
        <h3 className="text-sm font-medium text-ink-muted">
          {zh ? "校准汇总（仅已判定样本）" : "Calibration summary (resolved only)"}
        </h3>
        {loading ? (
          <p className="mt-2 text-xs text-ink-muted">{t.loading}</p>
        ) : cal ? (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap gap-4 text-sm">
              <span className="text-ink-muted">
                {zh ? "已判定" : "resolved"}:{" "}
                <span className="font-mono text-ink">{cal.resolved}</span>
              </span>
              <span className="text-ink-muted">
                {zh ? "兑现" : "hits"}: <span className="font-mono text-ink">{cal.hits}</span>
              </span>
              <span className="text-ink-muted">
                {zh ? "未兑现" : "misses"}:{" "}
                <span className="font-mono text-ink">{cal.misses}</span>
              </span>
              {cal.brier !== null && cal.brier !== undefined ? (
                <span className="text-ink-muted">
                  Brier: <span className="font-mono text-ink">{cal.brier}</span>
                </span>
              ) : null}
              {cal.ece !== null && cal.ece !== undefined ? (
                <span className="text-ink-muted">
                  ECE: <span className="font-mono text-ink">{cal.ece}</span>
                </span>
              ) : null}
            </div>
            {cal.mixed_providers && cal.mixed_providers.length > 1 ? (
              <p className="text-xs text-amber-300/90">{cal.note ?? ""}</p>
            ) : null}
            {reliability.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-[11px] text-ink-muted">
                  {zh ? "可靠性曲线（预测概率 vs 实际兑现率）" : "Reliability curve"}
                </p>
                {reliability.map((bucket) => (
                  <div key={bucket.range} className="flex items-center gap-2">
                    <span className="w-20 shrink-0 font-mono text-[11px] text-ink-muted">
                      {bucket.range}
                    </span>
                    <span className="h-3 flex-1 overflow-hidden rounded bg-line/30">
                      <span
                        className="block h-3 rounded bg-accent"
                        style={{
                          width: `${maxReliabilityCount > 0 ? Math.round((bucket.count / maxReliabilityCount) * 100) : 0}%`,
                        }}
                      />
                    </span>
                    <span className="w-28 shrink-0 text-right text-[11px] text-ink-muted">
                      {zh ? "预测" : "pred"} {bucket.mean_probability} · {zh ? "实际" : "actual"}{" "}
                      {bucket.empirical_rate}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-2 text-xs text-ink-muted">{t.errorFeed}</p>
        )}
      </div>

      {/* 预测登记列表 */}
      <div className="rounded-xl border border-line bg-surface-muted/40 p-5">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-medium text-ink-muted">
            {zh ? "推演登记（可被证伪）" : "Registered projections (falsifiable)"}
          </h3>
          <span className="text-[11px] text-ink-muted">
            {predictions.data?.total ?? 0} {zh ? "条" : "total"}
          </span>
        </div>
        {loading ? (
          <p className="mt-2 text-xs text-ink-muted">{t.loading}</p>
        ) : items.length === 0 ? (
          <p className="mt-2 text-xs text-ink-muted">
            {zh ? "还没有登记任何推演。" : "No projections registered yet."}
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {items.map((p) => (
              <li key={p.id} className="rounded-lg border border-line/70 p-3">
                <p className="text-sm text-ink/90">
                  {zh ? p.statement_zh || p.statement_en : p.statement_en || p.statement_zh}
                </p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                  <span className="font-mono text-ink">
                    {Math.round(p.predicted_probability * 100)}%
                  </span>
                  <span>·</span>
                  <span>{STATUS_LABEL[p.status]?.[zh ? "zh" : "en"] ?? p.status}</span>
                  <span>·</span>
                  <span>{p.provider || "—"}</span>
                  <span>·</span>
                  <span>{fmtDate(p.due_at, zh)}</span>
                  <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[11px] text-rose-300">
                    {zh ? "未经校准" : "uncalibrated"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
