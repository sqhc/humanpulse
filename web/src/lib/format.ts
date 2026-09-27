import type { Lang } from "../i18n";

/** 时间展示：优先用当地时间，缺失时给一个明确的占位符而不是空白。 */
export function formatDateTime(value: string | null | undefined, lang: Lang): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function scoreClassName(score: number | null | undefined): string {
  if (score === null || score === undefined) return "border-line text-ink-muted";
  if (score >= 70) return "border-accent text-accent";
  if (score >= 40) return "border-amber-400/70 text-amber-300";
  return "border-line text-ink-muted";
}
