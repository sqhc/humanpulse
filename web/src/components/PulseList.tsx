import type { PulseCard } from "@humanpulse/api-client";

import type { Lang, Messages } from "../i18n";

/** 主题配色（与 Feed/DocumentCard 同一套语义色）。 */
const SECTION_THEMES: Record<string, string> = {
  conflict: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  science: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  labor: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  other: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

const SECTION_LABELS: Record<string, { zh: string; en: string }> = {
  conflict: { zh: "冲突", en: "Conflict" },
  science: { zh: "科技", en: "Science" },
  labor: { zh: "劳工", en: "Labour" },
  other: { zh: "其他", en: "Other" },
};

interface PulseListProps {
  pulses: PulseCard[];
  lang: Lang;
  t: Messages;
}

/**
 * 脉搏短讯列表：事实一句 + 钩子（为什么重要 / 接下来看什么）。
 *
 * 数据来自简报生成时产出的 `structured.pulses`——前端零模型调用。
 * 老简报没有该字段时列表为空，此处不渲染（由调用方判断）。
 * 钩子缺失时只渲染事实行，不编造「为什么重要」。
 */
export function PulseList({ pulses, lang, t }: PulseListProps) {
  const zh = lang === "zh";
  const usable = pulses.filter((pulse) => (zh ? pulse.fact_zh : pulse.fact_en)?.trim());
  if (usable.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3" data-testid="pulse-list">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-ink-muted">{t.briefPulses}</h3>
        <span className="text-[11px] text-ink-muted">{t.briefPulsesHint}</span>
      </div>
      <ul className="space-y-2">
        {usable.map((pulse, index) => {
          const key = pulse.section_key ?? "other";
          const fact = (zh ? pulse.fact_zh : pulse.fact_en)?.trim() ?? "";
          const hook = (zh ? pulse.hook_zh : pulse.hook_en)?.trim() ?? "";
          const label = SECTION_LABELS[key] ?? SECTION_LABELS.other;
          return (
            <li
              key={`${key}-${index}`}
              className="rounded-xl border border-line bg-surface-muted/40 p-3"
            >
              <div className="flex items-start gap-2">
                <span
                  className={`shrink-0 rounded px-2 py-0.5 text-[11px] ring-1 ${
                    SECTION_THEMES[key] ?? SECTION_THEMES.other
                  }`}
                >
                  {zh ? label.zh : label.en}
                </span>
                <p className="text-sm leading-snug text-ink/90">{fact}</p>
              </div>
              {hook ? (
                <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                  <span className="text-accent">→ </span>
                  {hook}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
