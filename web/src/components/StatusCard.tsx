import type { ReadyResponse } from "@humanpulse/api-client";
import type { Messages } from "../i18n";

export type StatusState = "loading" | "ok" | "degraded" | "unreachable";

interface StatusCardProps {
  t: Messages;
  state: StatusState;
  version?: string;
  ready?: ReadyResponse;
  errorMessage?: string;
}

const dotClass: Record<StatusState, string> = {
  loading: "bg-ink-muted",
  ok: "bg-accent",
  degraded: "bg-amber-400",
  unreachable: "bg-red-400",
};

export function StatusCard({ t, state, version, ready, errorMessage }: StatusCardProps) {
  const label =
    state === "ok"
      ? t.statusOk
      : state === "degraded"
        ? t.statusDegraded
        : state === "unreachable"
          ? t.statusUnreachable
          : t.statusLoading;

  return (
    <section className="rounded-xl border border-line bg-surface-muted/60 p-5">
      <div className="flex items-center gap-3">
        <span className={`h-2.5 w-2.5 rounded-full ${dotClass[state]}`} aria-hidden="true" />
        <h2 className="text-sm font-medium text-ink-muted">{t.statusTitle}</h2>
      </div>
      <p className="mt-2 text-lg font-semibold" data-testid="status-label">
        {label}
      </p>
      {version ? (
        <p className="mt-1 text-sm text-ink-muted">
          {t.apiVersion}: <span className="font-mono">{version}</span>
        </p>
      ) : null}
      {ready ? (
        <ul className="mt-3 space-y-1 text-sm text-ink-muted">
          {ready.components.map((c) => (
            <li key={c.name}>
              <span className="font-mono">{c.name}</span>: {c.ok ? "ok" : "down"}
            </li>
          ))}
        </ul>
      ) : null}
      {errorMessage ? <p className="mt-2 text-sm text-red-300">{errorMessage}</p> : null}
      {state !== "ok" ? <p className="mt-3 text-sm text-ink-muted">{t.statusHint}</p> : null}
    </section>
  );
}
