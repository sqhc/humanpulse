import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";

interface DocumentDetailViewProps {
  id: number;
  lang: Lang;
  t: Messages;
}

export function DocumentDetailView({ id, lang, t }: DocumentDetailViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const query = useQuery({
    queryKey: ["document", id],
    queryFn: ({ signal }) => api.getDocument(id, { signal }),
  });

  if (query.isPending) {
    return <p className="text-sm text-ink-muted">{t.loading}</p>;
  }
  if (query.isError || !query.data) {
    return (
      <div className="space-y-3">
        <p className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
          {t.notFound}
        </p>
        <a className="text-sm text-accent hover:underline" href="#/">
          ← {t.backToFeed}
        </a>
      </div>
    );
  }

  const doc = query.data;
  const tags = doc.tags ?? [];
  const siblings = doc.siblings ?? [];
  const headlineOnly = tags.includes("headline-only");

  return (
    <article className="space-y-4">
      <a className="text-sm text-accent hover:underline" href="#/">
        ← {t.backToFeed}
      </a>

      <header className="space-y-2">
        <h2 className="text-xl font-semibold leading-snug text-ink">{doc.title}</h2>
        <p className="text-xs text-ink-muted">
          {t.source}: {doc.source_name ?? "—"} · {t.published}: 
          {formatDateTime(doc.published_at ?? doc.fetched_at, lang)}
          {doc.language ? ` · ${doc.language}` : ""}
          {headlineOnly ? ` · ${t.headlineOnly}` : ""}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {doc.score !== null ? (
            <span className={`rounded-md border px-2 py-0.5 text-xs font-mono ${scoreClassName(doc.score)}`}>
              {t.score}: {doc.score}
            </span>
          ) : null}
          <span className="rounded bg-accent/10 px-2 py-0.5 text-[11px] text-accent">{t.aiSummary}</span>
          {tags
            .filter((tag) => tag !== "headline-only")
            .map((tag) => (
              <span key={tag} className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted">
                {tag}
              </span>
            ))}
        </div>
      </header>

      <section className="space-y-3 rounded-xl border border-line bg-surface-muted/40 p-4">
        {doc.summary_zh ? (
          <div>
            <h3 className="text-xs uppercase tracking-wide text-ink-muted">中文摘要</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink/90">{doc.summary_zh}</p>
          </div>
        ) : null}
        {doc.summary_en ? (
          <div>
            <h3 className="text-xs uppercase tracking-wide text-ink-muted">English summary</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink/90">{doc.summary_en}</p>
          </div>
        ) : null}
        {doc.rationale ? (
          <div>
            <h3 className="text-xs uppercase tracking-wide text-ink-muted">{t.rationale}</h3>
            <p className="mt-1 text-sm text-ink-muted">{doc.rationale}</p>
          </div>
        ) : null}
        <a
          className="inline-block text-sm text-accent hover:underline"
          href={doc.url}
          target="_blank"
          rel="noreferrer noopener"
        >
          {t.openOriginal} ↗
        </a>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-medium text-ink-muted">{t.sameEvent}</h3>
        {siblings.length === 0 ? (
          <p className="text-sm text-ink-muted">{t.noSiblings}</p>
        ) : (
          <ul className="space-y-2">
            {siblings.map((sibling) => (
              <li key={sibling.id} className="rounded-lg border border-line/70 p-3">
                <a className="text-sm text-ink hover:text-accent" href={documentHref(sibling.id)}>
                  {sibling.title}
                </a>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {sibling.source_name ?? "—"} · {formatDateTime(sibling.published_at ?? sibling.fetched_at, lang)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
