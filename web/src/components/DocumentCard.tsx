import type { DocumentOut } from "@humanpulse/api-client";
import type { ReactNode } from "react";

import type { Lang, Messages } from "../i18n";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";

/** 话题标签主题配色：conflict=玫红 / science=青蓝 / labor=琥珀 / other=灰。 */
const TAG_THEMES: Record<string, string> = {
  conflict: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  science: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  labor: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  other: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

function tagTheme(tag: string): string {
  return TAG_THEMES[tag] ?? "bg-line/40 text-ink-muted";
}

/** 把正文里的地区名浅底高亮（地区=青色主题，区别于话题标签配色）。 */
function highlightRegions(text: string, regions: string[]): ReactNode {
  const escaped = regions
    .filter(Boolean)
    .map((r) => r.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  return text.split(pattern).map((part, index) =>
    index % 2 === 1 ? (
      <mark key={index} className="rounded bg-teal-500/20 px-0.5 text-teal-200">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

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
  const regions = doc.regions ?? [];
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

      {body ? <p className="mt-2 line-clamp-3 text-sm text-ink/90">{highlightRegions(body, regions)}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-accent/10 px-2 py-0.5 text-[11px] text-accent">{t.aiSummary}</span>
        {visibleTags.map((tag) => (
          <span key={tag} className={`rounded px-2 py-0.5 text-[11px] ring-1 ${tagTheme(tag)}`}>
            {tag}
          </span>
        ))}
      </div>
    </article>
  );
}
