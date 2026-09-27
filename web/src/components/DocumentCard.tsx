import type { DocumentOut } from "@humanpulse/api-client";

import type { Lang, Messages } from "../i18n";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";

interface DocumentCardProps {
  doc: DocumentOut;
  lang: Lang;
  t: Messages;
}

export function DocumentCard({ doc, lang, t }: DocumentCardProps) {
  const summary = lang === "zh" ? doc.summary_zh : doc.summary_en;
  const fallback = lang === "zh" ? doc.summary_en : doc.summary_zh;
  const body = summary || fallback;
  const tags = doc.tags ?? [];
  const headlineOnly = tags.includes("headline-only");
  const visibleTags = tags.filter((tag) => tag !== "headline-only").slice(0, 6);

  return (
    <article className="rounded-xl border border-line bg-surface-muted/40 p-4 transition hover:border-accent/60">
      <div className="flex items-start justify-between gap-3">
        <a
          href={documentHref(doc.id)}
          className="text-base font-semibold leading-snug text-ink hover:text-accent"
          data-testid="document-title"
        >
          {doc.title}
        </a>
        {doc.score !== null ? (
          <span
            className={`shrink-0 rounded-md border px-2 py-0.5 text-xs font-mono ${scoreClassName(doc.score)}`}
            title={t.score}
          >
            {doc.score}
          </span>
        ) : null}
      </div>

      <p className="mt-1 text-xs text-ink-muted">
        {doc.source_name ?? "—"} · {formatDateTime(doc.published_at ?? doc.fetched_at, lang)}
        {headlineOnly ? ` · ${t.headlineOnly}` : ""}
      </p>

      {body ? <p className="mt-2 line-clamp-3 text-sm text-ink/90">{body}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-accent/10 px-2 py-0.5 text-[11px] text-accent">{t.aiSummary}</span>
        {visibleTags.map((tag) => (
          <span key={tag} className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted">
            {tag}
          </span>
        ))}
      </div>
    </article>
  );
}
