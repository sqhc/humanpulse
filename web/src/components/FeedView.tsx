import type { DocumentOut } from "@humanpulse/api-client";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { useDocumentStream } from "../lib/useDocumentStream";
import { DocumentCard } from "./DocumentCard";
import { emptyFilters, FilterBar, type FeedFilters } from "./FilterBar";

const PAGE_SIZE = 20;

interface FeedViewProps {
  lang: Lang;
  t: Messages;
}

export function FeedView({ lang, t }: FeedViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const [filters, setFilters] = useState<FeedFilters>(emptyFilters);
  const [liveCount, setLiveCount] = useState(0);
  const queryClient = useQueryClient();
  const refreshing = useRef(false);

  // SSE：每条新文档只累加计数；5 秒内的多次事件合并成一次刷新，避免打爆接口
  const handleDocument = useCallback(() => {
    setLiveCount((count) => count + 1);
    if (refreshing.current) return;
    refreshing.current = true;
    window.setTimeout(() => {
      refreshing.current = false;
      void queryClient.invalidateQueries({ queryKey: ["feed"] });
    }, 5000);
  }, [queryClient]);
  const stream = useDocumentStream(handleDocument);

  const feed = useInfiniteQuery({
    queryKey: ["feed", filters],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam, signal }) =>
      api.listDocuments(
        {
          limit: PAGE_SIZE,
          cursor: pageParam ?? undefined,
          lang: filters.lang || undefined,
          kind: filters.kind || undefined,
          min_score: filters.minScore > 0 ? filters.minScore : undefined,
          q: filters.q.trim() || undefined,
        },
        { signal },
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const items: DocumentOut[] = feed.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">{t.feedTitle}</h2>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-ink-muted">
            <span
              data-testid="stream-status"
              className={
                stream.status === "open"
                  ? "h-2 w-2 rounded-full bg-accent"
                  : "h-2 w-2 rounded-full bg-ink-muted/60"
              }
            />
            {stream.status === "open"
              ? t.streamLive
              : stream.status === "connecting"
                ? t.streamConnecting
                : t.streamOffline}
          </span>
          {liveCount > 0 ? (
            <span className="text-accent">
              {t.streamReceived}: {liveCount}
            </span>
          ) : null}
        </div>
        <p className="text-xs text-ink-muted">{t.aiSummaryNotice}</p>
      </div>

      <FilterBar t={t} filters={filters} onChange={setFilters} />

      {feed.isPending ? <p className="text-sm text-ink-muted">{t.loading}</p> : null}

      {feed.isError ? (
        <div className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
          <p>{t.errorFeed}</p>
          <button
            type="button"
            className="mt-2 rounded-md border border-red-400/50 px-3 py-1 text-xs hover:bg-red-500/10"
            onClick={() => void feed.refetch()}
          >
            {t.retry}
          </button>
        </div>
      ) : null}

      {!feed.isPending && !feed.isError && items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface-muted/40 p-4 text-sm text-ink-muted">
          {t.emptyFeed}
        </p>
      ) : null}

      <div className="space-y-3">
        {items.map((doc) => (
          <DocumentCard key={doc.id} doc={doc} lang={lang} t={t} />
        ))}
      </div>

      <div className="flex items-center justify-center gap-3 pt-2">
        {feed.hasNextPage ? (
          <button
            type="button"
            className="rounded-md border border-line px-4 py-2 text-sm text-ink transition hover:border-accent hover:text-accent disabled:opacity-50"
            disabled={feed.isFetchingNextPage}
            onClick={() => void feed.fetchNextPage()}
          >
            {feed.isFetchingNextPage ? t.loading : t.loadMore}
          </button>
        ) : items.length > 0 ? (
          <p className="text-xs text-ink-muted">{t.noMore}</p>
        ) : null}
      </div>
    </section>
  );
}
