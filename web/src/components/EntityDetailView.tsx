import { ApiError } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";

const TIMELINE_DAYS = 90;
const RECENT_LIMIT = 30;

interface EntityDetailViewProps {
  id: number;
  lang: Lang;
  t: Messages;
}

export function EntityDetailView({ id, lang, t }: EntityDetailViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const query = useQuery({
    queryKey: ["entity", id],
    queryFn: ({ signal }) =>
      api.getEntity(id, { days: TIMELINE_DAYS, recent_limit: RECENT_LIMIT }, { signal }),
  });

  const notFound = query.error instanceof ApiError && query.error.status === 404;

  if (query.isPending) {
    return <p className="text-sm text-ink-muted">{t.loading}</p>;
  }
  if (query.isError || !query.data) {
    return (
      <div className="space-y-3">
        <a className="text-sm text-accent hover:underline" href="#/entities">
          ← {t.entityBack}
        </a>
        <p className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
          {notFound ? t.notFound : t.errorFeed}
        </p>
      </div>
    );
  }

  const entity = query.data;
  const aliases = entity.aliases ?? [];
  const timeline = entity.timeline ?? [];
  const recent = entity.recent ?? [];
  const maxCount = timeline.reduce((max, point) => Math.max(max, point.count), 0);

  return (
    <article className="space-y-5">
      <a className="text-sm text-accent hover:underline" href="#/entities">
        ← {t.entityBack}
      </a>

      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-xl font-semibold text-ink">{entity.name}</h2>
          <span className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted">
            {entity.kind}
          </span>
        </div>
        {aliases.length > 0 ? (
          <p className="text-xs text-ink-muted">
            {t.entityAliases}: {aliases.join(" / ")}
          </p>
        ) : null}
        <p className="text-xs text-ink-muted">
          {t.entityFirstSeen}: {formatDateTime(entity.first_seen_at, lang)} · {t.entityLastSeen}:{" "}
          {formatDateTime(entity.last_seen_at, lang)} · {t.entitiesMentions}: {entity.mention_count}
        </p>
      </header>

      <section className="space-y-2">
        <h3 className="text-sm font-medium text-ink-muted">{t.entityTimeline}</h3>
        {timeline.length === 0 ? (
          <p className="text-sm text-ink-muted">{t.entityNoTimeline}</p>
        ) : (
          <ul className="space-y-1.5">
            {timeline.map((point) => (
              <li key={point.day} className="flex items-center gap-2">
                <span className="w-24 shrink-0 font-mono text-xs text-ink-muted">
                  {point.day}
                </span>
                <span className="h-3 flex-1 overflow-hidden rounded bg-line/30">
                  <span
                    data-testid="timeline-bar"
                    className="block h-3 rounded bg-accent"
                    style={{
                      width: `${maxCount > 0 ? Math.round((point.count / maxCount) * 100) : 0}%`,
                    }}
                  />
                </span>
                <span className="w-8 shrink-0 text-right text-xs text-ink-muted">
                  {point.count}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-medium text-ink-muted">{t.entityRecent}</h3>
        {recent.length === 0 ? (
          <p className="text-sm text-ink-muted">{t.entityNoTimeline}</p>
        ) : (
          <ul className="space-y-2">
            {recent.map((mention) => (
              <li
                key={`${mention.document_id}-${mention.published_at}`}
                className="rounded-lg border border-line/70 p-3"
              >
                <a
                  className="text-sm text-ink hover:text-accent"
                  href={documentHref(mention.document_id)}
                >
                  {mention.title}
                </a>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {mention.source_name ?? "—"} · {formatDateTime(mention.published_at, lang)}
                </p>
                {mention.score !== null && mention.score !== undefined ? (
                  <span
                    className={`mt-1 inline-block rounded-md border px-2 py-0.5 text-xs font-mono ${scoreClassName(
                      mention.score,
                    )}`}
                  >
                    {t.score}: {mention.score}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
