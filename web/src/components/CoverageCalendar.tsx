import type { CoverageCalendarOut, CoverageDayOut } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";

/** 日历要展示的天数（行数按 7 列网格自适应）。 */
const CALENDAR_DAYS = 30;

type CoverageState = "normal" | "idle" | "gap" | "noLedger";

/** 三态 + 无底账：口径见后端 coverage.py —— 断档是「没采」，无底账是「没记录」。 */
function dayState(day: CoverageDayOut, earliest: string | null): CoverageState {
  if (earliest && day.date < earliest) return "noLedger";
  if (day.collected > 0 && day.enriched === 0) return "idle";
  if (day.collected > 0) return "normal";
  return "gap";
}

/** 正常日饱和度 ∝ log(enriched+1)，上限 4 档。 */
function intensityClass(day: CoverageDayOut): string {
  const level = Math.min(4, Math.floor(Math.log2(day.enriched + 1)));
  return ["bg-accent/15", "bg-accent/30", "bg-accent/50", "bg-accent/70", "bg-accent"][level];
}

interface CoverageCalendarProps {
  lang: Lang;
  t: Messages;
}

export function CoverageCalendar({ lang, t }: CoverageCalendarProps) {
  const api = createApiClient();
  const calendar = useQuery({
    queryKey: ["coverage", CALENDAR_DAYS],
    queryFn: ({ signal }) => api.getCoverageCalendar(CALENDAR_DAYS, { signal }),
  });

  if (calendar.isPending) return <p className="text-sm text-ink-muted">{t.loading}</p>;
  if (calendar.isError) return null;

  const data: CoverageCalendarOut | undefined = calendar.data;
  if (!data) return null;

  const earliest = data.earliest_ledger_date ?? null;
  const days = data.days ?? [];
  const stateClass: Record<CoverageState, string> = {
    normal: intensityClass,
    idle: () => "bg-amber-500/50",
    gap: () => "bg-slate-600/40 coverage-gap",
    noLedger: () => "bg-line/20",
  } as unknown as Record<CoverageState, string>;
  const stateLabel: Record<CoverageState, (m: Messages) => string> = {
    normal: (m) => m.coverageNormal,
    idle: (m) => m.coverageIdle,
    gap: (m) => m.coverageGapped,
    noLedger: (m) => m.coverageNoLedger,
  };

  return (
    <section
      className="rounded-xl border border-line bg-surface-muted/40 p-4"
      data-testid="coverage-calendar"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">{t.coverageTitle}</h3>
        <p className="text-xs text-ink-muted">{t.coverageRelativeNote}</p>
      </header>

      <div className="mt-3 grid grid-cols-10 gap-1" role="img" aria-label={t.coverageTitle}>
        {days.map((day) => {
          const state = dayState(day, earliest);
          const cls = state === "normal" ? intensityClass(day) : (stateClass[state] as string);
          const hover =
            state === "gap" || state === "noLedger"
              ? stateLabel[state](t)
              : `${stateLabel[state](t)} · ${t.coverageCollected} ${day.collected} / ${t.coverageEnriched} ${day.enriched}`;
          return (
            <a
              key={day.date}
              href={`#/?since=${day.date}T00:00:00&until=${day.date}T23:59:59`}
              title={`${day.date} · ${hover}`}
              className={`aspect-square rounded ${cls} transition hover:ring-1 hover:ring-accent`}
              data-state={state}
            />
          );
        })}
      </div>

      <p className="mt-2 text-xs text-ink-muted">
        {t.coverageSummary
          .replace("{collected}", String(data.total_collected))
          .replace("{enriched}", String(data.total_enriched))}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded bg-accent" /> {t.coverageNormal}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded bg-amber-500/50" /> {t.coverageIdle}
        </span>
        <span className="flex items-center gap-1">
          <span className="coverage-gap h-2 w-2 rounded bg-slate-600/40" /> {t.coverageGapped}
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded bg-line/20" /> {t.coverageNoLedger}
        </span>
        <span>{lang === "zh" ? "点击某天查看当天 Feed" : "click a day to open its feed"}</span>
      </div>
    </section>
  );
}
