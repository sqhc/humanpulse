import type { JobName, SourceOut } from "@humanpulse/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime } from "../lib/format";

/** localStorage 里保存管理员 API Key 的键名（只落在本机浏览器）。 */
const ADMIN_KEY_STORAGE = "humanpulse.adminApiKey";

const secondaryButtonClass =
  "rounded-lg border border-line px-3 py-1.5 text-xs text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40";

function readStoredKey(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(ADMIN_KEY_STORAGE) ?? "";
}

interface SectionStateProps {
  message: string;
  error?: boolean;
}

function SectionState({ message, error = false }: SectionStateProps) {
  return (
    <p
      className={
        error
          ? "rounded-xl border border-red-400/40 bg-red-500/5 p-3 text-sm text-red-200"
          : "rounded-xl border border-line bg-surface-muted/40 p-3 text-sm text-ink-muted"
      }
    >
      {message}
    </p>
  );
}

interface AdminViewProps {
  t: Messages;
  lang: Lang;
}

interface RunJobInput {
  job: JobName;
  params?: { force?: boolean; limit?: number; kind?: "daily" | "weekly" };
}

export function AdminView({ t, lang }: AdminViewProps) {
  const [apiKey, setApiKey] = useState(readStoredKey);
  const [draftKey, setDraftKey] = useState(readStoredKey);
  const [jobStats, setJobStats] = useState<Record<string, unknown> | null>(null);

  const api = useMemo(() => createApiClient(apiKey), [apiKey]);
  const queryClient = useQueryClient();

  const sources = useQuery({
    queryKey: ["admin", "sources", apiKey],
    queryFn: ({ signal }) => api.listSources({ signal }),
  });

  const runs = useQuery({
    queryKey: ["admin", "runs", apiKey],
    queryFn: ({ signal }) => api.listRuns(20, { signal }),
    enabled: Boolean(apiKey),
  });

  const usage = useQuery({
    queryKey: ["admin", "usage", apiKey],
    queryFn: ({ signal }) => api.listUsage(7, { signal }),
    enabled: Boolean(apiKey),
  });

  const toggleSource = useMutation({
    mutationFn: (source: SourceOut) =>
      api.updateSource(source.id, { enabled: !source.enabled }, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "sources"] });
    },
  });

  const runJob = useMutation({
    mutationFn: (input: RunJobInput) => api.runJob(input.job, input.params ?? {}, {}),
    onSuccess: (data) => {
      setJobStats(data.stats);
    },
  });

  const handleSaveKey = () => {
    const next = draftKey.trim();
    setApiKey(next);
    if (typeof window === "undefined") {
      return;
    }
    if (next) {
      window.localStorage.setItem(ADMIN_KEY_STORAGE, next);
    } else {
      window.localStorage.removeItem(ADMIN_KEY_STORAGE);
    }
  };

  const handleClearKey = () => {
    setDraftKey("");
    setApiKey("");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(ADMIN_KEY_STORAGE);
    }
  };

  const handleRefresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin", "sources"] });
    void queryClient.invalidateQueries({ queryKey: ["admin", "runs"] });
    void queryClient.invalidateQueries({ queryKey: ["admin", "usage"] });
  };

  const sourceRows = sources.data ?? [];
  const runRows = runs.data ?? [];
  const usageRows = usage.data ?? [];

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">{t.adminKeyTitle}</h2>
            <p className="text-xs text-ink-muted">{t.adminKeyHint}</p>
          </div>
          <button type="button" onClick={handleRefresh} className={secondaryButtonClass}>
            {t.adminRefresh}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={draftKey}
            onChange={(event) => setDraftKey(event.target.value)}
            aria-label={t.adminKeyTitle}
            autoComplete="off"
            className="min-w-0 flex-1 rounded-lg border border-line bg-surface-muted/40 px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <button type="button" onClick={handleSaveKey} className={secondaryButtonClass}>
            {t.adminKeySave}
          </button>
          <button type="button" onClick={handleClearKey} className={secondaryButtonClass}>
            {t.adminKeyClear}
          </button>
        </div>
        {apiKey ? null : <p className="text-xs text-amber-300">{t.adminKeyMissing}</p>}
      </section>

      <section className="space-y-3">
        <header>
          <h2 className="text-lg font-semibold text-ink">{t.adminSources}</h2>
          <p className="text-xs text-ink-muted">{t.adminSourcesHint}</p>
        </header>
        {sources.isPending ? (
          <SectionState message={t.loading} />
        ) : sources.isError ? (
          <SectionState message={t.errorFeed} error />
        ) : sourceRows.length === 0 ? (
          <SectionState message={t.adminEmpty} />
        ) : (
          <ul className="space-y-2">
            {sourceRows.map((source) => (
              <li
                key={source.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface-muted/40 p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{source.name}</p>
                  <p className="text-xs text-ink-muted">
                    {t.adminSrcMeta}: {source.kind} · tier {source.tier} · {source.cadence_minutes}min
                  </p>
                  <p className="text-xs text-ink-muted">
                    {t.adminSourceStatus}: {source.last_status ?? "—"} · {t.adminSourceLastRun}:{" "}
                    {formatDateTime(source.last_run_at, lang)} · {t.adminSourceFailures}:{" "}
                    {source.consecutive_failures}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={!apiKey || toggleSource.isPending}
                  onClick={() => toggleSource.mutate(source)}
                  className={secondaryButtonClass}
                >
                  {source.enabled ? t.adminSourceDisable : t.adminSourceEnable}
                </button>
              </li>
            ))}
          </ul>
        )}
        {toggleSource.isError ? <SectionState message={t.errorFeed} error /> : null}
      </section>

      <section className="space-y-3">
        <header>
          <h2 className="text-lg font-semibold text-ink">{t.adminJobs}</h2>
          <p className="text-xs text-ink-muted">{t.adminJobsHint}</p>
        </header>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={runJob.isPending}
            onClick={() => runJob.mutate({ job: "collect", params: { force: true } })}
            className={secondaryButtonClass}
          >
            {t.adminRunCollect}
          </button>
          <button
            type="button"
            disabled={runJob.isPending}
            onClick={() => runJob.mutate({ job: "process", params: { limit: 20 } })}
            className={secondaryButtonClass}
          >
            {t.adminRunProcess}
          </button>
          <button
            type="button"
            disabled={runJob.isPending}
            onClick={() =>
              runJob.mutate({ job: "brief", params: { force: true, kind: "daily" } })
            }
            className={secondaryButtonClass}
          >
            {t.adminRunBriefDaily}
          </button>
          <button
            type="button"
            disabled={runJob.isPending}
            onClick={() =>
              runJob.mutate({ job: "brief", params: { force: true, kind: "weekly" } })
            }
            className={secondaryButtonClass}
          >
            {t.adminRunBriefWeekly}
          </button>
        </div>
        {runJob.isPending ? <p className="text-sm text-ink-muted">{t.adminRunning}</p> : null}
        {runJob.isError ? <SectionState message={t.errorFeed} error /> : null}
        {jobStats ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">{t.adminJobResult}</h3>
            <pre className="overflow-x-auto rounded-xl border border-line bg-surface-muted/40 p-3 text-xs text-ink">
              {JSON.stringify(jobStats, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">{t.adminRuns}</h2>
        {!apiKey ? (
          <SectionState message={t.adminEmpty} />
        ) : runs.isPending ? (
          <SectionState message={t.loading} />
        ) : runs.isError ? (
          <SectionState message={t.errorFeed} error />
        ) : runRows.length === 0 ? (
          <SectionState message={t.adminEmpty} />
        ) : (
          <ul className="space-y-2">
            {runRows.map((run) => (
              <li key={run.id} className="rounded-xl border border-line bg-surface-muted/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="truncate text-ink">{run.source_name ?? run.source_id}</span>
                  <span className="text-ink-muted">{run.status}</span>
                </div>
                <p className="text-xs text-ink-muted">
                  {formatDateTime(run.started_at, lang)} · {t.adminSeen} {run.items_seen} ·{" "}
                  {t.adminNew} {run.items_new} · {t.adminRejected} {run.items_rejected}
                </p>
                {run.error ? <p className="mt-1 text-xs text-red-300">{run.error}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-ink">{t.adminUsage}</h2>
        {!apiKey ? (
          <SectionState message={t.adminEmpty} />
        ) : usage.isPending ? (
          <SectionState message={t.loading} />
        ) : usage.isError ? (
          <SectionState message={t.errorFeed} error />
        ) : usageRows.length === 0 ? (
          <SectionState message={t.adminEmpty} />
        ) : (
          <ul className="space-y-2">
            {usageRows.map((row) => (
              <li
                key={`${row.day}-${row.provider}-${row.model}`}
                className="rounded-xl border border-line bg-surface-muted/40 p-3 text-xs text-ink-muted"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="text-ink">{row.model}</span>
                  <span>{row.day}</span>
                </div>
                <p>
                  {t.adminCalls} {row.calls} · {t.adminTokensIn} {row.tokens_in} ·{" "}
                  {t.adminTokensOut} {row.tokens_out} · {t.adminCost} ${row.cost_usd.toFixed(4)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
