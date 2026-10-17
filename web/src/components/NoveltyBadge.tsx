import type { Lang, Messages } from "../i18n";

export type NoveltyBand = "high" | "mid" | "covered";

interface NoveltyBadgeProps {
  /** 后端给的相对档位：high=相对新颖 / mid=普通 / covered=近期已覆盖 */
  band: NoveltyBand | string | null | undefined;
  /** 0-100 的相对百分位；仅用于悬停提示，不在徽标上显示数字 */
  percentile?: number | null;
  /** cohort 样本不足时前端只显示 band，不显示具体百分位 */
  cohortFallback?: boolean;
  t: Messages;
  lang: Lang;
}

/**
 * Signal 相对新颖度徽标。
 *
 * 诚实口径：这是「相对近期 cohort 的切分」，不是绝对校准——悬停里始终带
 * 「相对切分（非绝对校准）」。cohort 样本不足（fallback）或百分位 < 1 时，
 * 不显示「比 N% 更新」这类会说出荒谬数字的文案，只保留 band 标签。
 */
export function NoveltyBadge({
  band,
  percentile,
  cohortFallback = false,
  t,
  lang,
}: NoveltyBadgeProps) {
  if (band !== "high" && band !== "covered") {
    return null;
  }
  const zh = lang === "zh";
  const label = band === "high" ? t.noveltyHigh : t.noveltyCovered;
  const showPercentile =
    !cohortFallback &&
    percentile !== null &&
    percentile !== undefined &&
    Number.isFinite(percentile) &&
    percentile >= 1;
  const percentileText = showPercentile
    ? zh
      ? ` · 比 ${percentile}% 的近期报道更新`
      : ` · newer than ${percentile}% of recent reports`
    : "";
  const tooltip = `${label}${percentileText} · ${t.noveltyRelativeNote}`;
  const className =
    band === "high"
      ? "rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] text-emerald-300"
      : "rounded bg-slate-500/20 px-2 py-0.5 text-[11px] text-slate-400";

  return (
    <span className={className} title={tooltip} data-testid="novelty-badge">
      {label}
    </span>
  );
}
