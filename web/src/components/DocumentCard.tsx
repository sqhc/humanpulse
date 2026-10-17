import type { DocumentOut } from "@humanpulse/api-client";
import type { ReactNode } from "react";

import type { Lang, Messages } from "../i18n";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";
import { NoveltyBadge } from "./NoveltyBadge";

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

/** 按主题浅底高亮正文里的关键词（实体=紫 / 地区=青，区别于话题标签配色）。 */
function highlightKeywords(
  text: string,
  keywords: { word: string; className: string }[],
): ReactNode {
  const items = keywords
    .filter((k) => k.word.trim().length > 0)
    .map((k) => ({ word: k.word.trim(), className: k.className }))
    .sort((a, b) => b.word.length - a.word.length);
  if (items.length === 0) return text;
  const escaped = items.map((k) => k.word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  const themeByWord = new Map(items.map((k) => [k.word, k.className]));
  return text.split(pattern).map((part, index) => {
    if (index % 2 !== 1) return part;
    const className = themeByWord.get(part) ?? "";
    return (
      <mark key={index} className={`rounded px-0.5 ${className}`}>
        {part}
      </mark>
    );
  });
}

interface DocumentCardProps {
  doc: DocumentOut;
  lang: Lang;
  t: Messages;
  /** 列表的 novelty cohort 样本不足时为 true：只显示 band，不显示百分位 */
  cohortFallback?: boolean;
}

export function DocumentCard({ doc, lang, t, cohortFallback = false }: DocumentCardProps) {
  const summary = lang === "zh" ? doc.summary_zh : doc.summary_en;
  const fallback = lang === "zh" ? doc.summary_en : doc.summary_zh;
  const body = summary || fallback;
  const tags = doc.tags ?? [];
  const regions = doc.regions ?? [];
  const entityNames = (doc.entities ?? []).map((e) => e.name).filter(Boolean);
  const headlineOnly = tags.includes("headline-only");
  const visibleTags = tags.filter((tag) => tag !== "headline-only").slice(0, 6);
  const highlight = body
    ? highlightKeywords(body, [
        ...entityNames.map((name) => ({
          word: name,
          className: "bg-violet-500/20 text-violet-200",
        })),
        ...regions.map((r) => ({ word: r, className: "bg-teal-500/20 text-teal-200" })),
      ])
    : null;

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

      {body ? <p className="mt-2 line-clamp-3 text-sm text-ink/90">{highlight}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-accent/10 px-2 py-0.5 text-[11px] text-accent">{t.aiSummary}</span>
        <NoveltyBadge
          band={doc.band}
          percentile={doc.percentile}
          cohortFallback={cohortFallback}
          t={t}
          lang={lang}
        />
        {visibleTags.map((tag) => (
          <span key={tag} className={`rounded px-2 py-0.5 text-[11px] ring-1 ${tagTheme(tag)}`}>
            {tag}
          </span>
        ))}
      </div>
    </article>
  );
}
