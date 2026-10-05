import type { BriefContentShape } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime } from "../lib/format";

interface BriefViewProps {
  lang: Lang;
  t: Messages;
}

/** storyboard 接口中本组件实际使用的字段；后端可扩展，这里只取所需。 */
interface StoryboardSummary {
  scene_count?: number;
  total_seconds?: number;
}

/** 与 createApiClient 同源：留空则走同源反向代理。 */
const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

function contentOf(structured: Record<string, unknown> | undefined): BriefContentShape {
  return (structured ?? {}) as BriefContentShape;
}

function storyboardHref(briefId: number, lang: Lang): string {
  return `${apiBase}/api/v1/briefs/${briefId}/storyboard?language=${lang}`;
}

function subtitlesHref(briefId: number, lang: Lang): string {
  return `${apiBase}/api/v1/briefs/${briefId}/subtitles.srt?language=${lang}`;
}

async function fetchStoryboard(
  briefId: number,
  lang: Lang,
  signal: AbortSignal,
): Promise<StoryboardSummary> {
  const resp = await fetch(storyboardHref(briefId, lang), { signal });
  if (!resp.ok) {
    throw new Error(`storyboard 接口返回 ${resp.status}`);
  }
  return (await resp.json()) as StoryboardSummary;
}

export function BriefView({ lang, t }: BriefViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const [kind, setKind] = useState<"daily" | "weekly">("daily");
  const langCode = lang;

  const query = useQuery({
    queryKey: ["brief", "latest", kind],
    queryFn: ({ signal }) => api.getLatestBrief(kind, { signal }),
  });

  // 有简报才探测 storyboard；失败/加载中都不影响链接渲染。
  const briefId = query.data?.id;
  const storyboard = useQuery({
    queryKey: ["storyboard", briefId, langCode],
    enabled: briefId != null,
    queryFn: ({ signal }) => fetchStoryboard(briefId as number, langCode, signal),
  });

  if (query.isPending) {
    return <p className="text-sm text-ink-muted">{t.loading}</p>;
  }
  if (query.isError) {
    return (
      <p className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
        {t.errorFeed}
      </p>
    );
  }
  if (!query.data) {
    return (
      <p className="rounded-xl border border-line bg-surface-muted/40 p-4 text-sm text-ink-muted">
        {t.briefEmpty}
      </p>
    );
  }

  const brief = query.data;
  const content = contentOf(brief.structured);
  const zh = langCode === "zh";
  const title = (zh ? content.title_zh : content.title_en) || brief.title;
  const overview = zh ? content.overview_zh : content.overview_en;
  const closing = zh ? content.closing_zh : content.closing_en;
  const sections = content.sections ?? [];

  const sceneCount = storyboard.data?.scene_count;
  const totalSeconds = storyboard.data?.total_seconds;
  const scriptMetrics =
    typeof sceneCount === "number" && typeof totalSeconds === "number"
      ? `${sceneCount} · ${totalSeconds}s`
      : null;

  const toggleClass = (active: boolean) =>
    active
      ? "rounded-md border border-accent px-3 py-1 text-xs text-accent"
      : "rounded-md border border-line px-3 py-1 text-xs text-ink-muted transition hover:border-accent hover:text-accent";

  return (
    <article className="space-y-5">
      <header className="space-y-2">
        <div className="flex gap-2">
          <button
            type="button"
            className={toggleClass(kind === "daily")}
            onClick={() => setKind("daily")}
          >
            {t.briefKindDaily}
          </button>
          <button
            type="button"
            className={toggleClass(kind === "weekly")}
            onClick={() => setKind("weekly")}
          >
            {t.briefKindWeekly}
          </button>
        </div>
        <h2 className="text-xl font-semibold text-ink">{title}</h2>
        <p className="text-xs text-ink-muted">
          {t.briefPeriod}: {formatDateTime(brief.period_start, lang)} →{" "}
          {formatDateTime(brief.period_end, lang)} · {t.briefItems}: {brief.item_count} ·{" "}
          {brief.model}
        </p>
        {overview ? <p className="text-sm leading-relaxed text-ink/90">{overview}</p> : null}
        <a
          className="inline-block text-xs text-accent hover:underline"
          href={`/api/v1/briefs/${brief.id}/markdown?language=${langCode}`}
          target="_blank"
          rel="noreferrer noopener"
        >
          {t.briefRaw} ↗
        </a>
      </header>

      <div className="space-y-2 rounded-xl border border-line bg-surface-muted/40 p-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <a
            data-testid="brief-script-link"
            className="text-xs text-accent hover:underline"
            href={storyboardHref(brief.id, langCode)}
            download
          >
            {t.briefScript} ↓
          </a>
          <a
            data-testid="brief-srt-link"
            className="text-xs text-accent hover:underline"
            href={subtitlesHref(brief.id, langCode)}
            download
          >
            {t.briefSubtitles} ↓
          </a>
          {scriptMetrics ? (
            <span data-testid="brief-script-metrics" className="text-xs text-ink-muted">
              {scriptMetrics}
            </span>
          ) : null}
        </div>
        <p className="text-xs text-ink-muted">{t.briefVideoHint}</p>
      </div>

      {sections.map((section) => {
        const bullets = zh ? section.bullets_zh : section.bullets_en;
        if (!bullets || bullets.length === 0) {
          return null;
        }
        const heading = (zh ? section.heading_zh : section.heading_en) || section.key;
        return (
          <section key={section.key} className="rounded-xl border border-line bg-surface-muted/40 p-4">
            <h3 className="text-sm font-semibold text-accent">{heading}</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink/90">
              {bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          </section>
        );
      })}

      {closing ? <p className="text-sm text-ink-muted">{closing}</p> : null}
      <p className="text-xs text-ink-muted">{t.briefNotice}</p>
    </article>
  );
}
