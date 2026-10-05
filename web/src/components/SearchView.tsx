import type { SearchHitOut } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime, scoreClassName } from "../lib/format";
import { documentHref } from "../lib/router";

/** 语义搜索单次返回的上限；Phase 1 还没有分页接口。 */
const SEARCH_LIMIT = 20;
/** 短于这个长度的查询不发请求，避免无意义的向量检索。 */
const MIN_QUERY_LENGTH = 2;

interface SearchViewProps {
  lang: Lang;
  t: Messages;
}

export function SearchView({ lang, t }: SearchViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const [input, setInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const active = keyword.length >= MIN_QUERY_LENGTH;
  const tooShort = submitted && !active;

  const hits = useQuery({
    queryKey: ["search", keyword, lang],
    enabled: active,
    queryFn: ({ signal }) => api.search(keyword, { limit: SEARCH_LIMIT }, { signal }),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setKeyword(input.trim());
    setSubmitted(true);
  }

  const items: SearchHitOut[] = hits.data ?? [];

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">{t.searchTitle}</h2>
        <p className="text-xs text-ink-muted">{t.searchHint}</p>
      </header>

      <form className="flex flex-wrap gap-2" onSubmit={submit}>
        <input
          type="search"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t.searchPlaceholder}
          data-testid="search-input"
          className="min-w-0 flex-1 rounded-md border border-line bg-surface-muted/40 px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-md border border-line px-4 py-1.5 text-sm text-ink transition hover:border-accent hover:text-accent"
        >
          {t.searchTitle}
        </button>
      </form>

      {tooShort ? (
        <p className="rounded-xl border border-line bg-surface-muted/40 p-4 text-sm text-ink-muted">
          {t.searchTooShort}
        </p>
      ) : null}

      {active && hits.isPending ? (
        <p className="text-sm text-ink-muted">{t.loading}</p>
      ) : null}

      {hits.isError ? (
        <p className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
          {t.errorFeed}
        </p>
      ) : null}

      {active && !hits.isPending && !hits.isError && items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface-muted/40 p-4 text-sm text-ink-muted">
          {t.searchEmpty}
        </p>
      ) : null}

      <ul className="space-y-2">
        {items.map((hit) => {
          const summary = lang === "zh" ? hit.summary_zh : hit.summary_en;
          const fallback = lang === "zh" ? hit.summary_en : hit.summary_zh;
          const body = summary || fallback;
          const tags = hit.tags ?? [];
          return (
            <li
              key={hit.document_id}
              className="rounded-xl border border-line bg-surface-muted/40 p-3"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a
                  className="text-sm font-medium text-ink hover:text-accent"
                  href={documentHref(hit.document_id)}
                >
                  {hit.title}
                </a>
                <div className="flex items-center gap-2">
                  {hit.score !== null && hit.score !== undefined ? (
                    <span
                      className={`shrink-0 rounded-md border px-2 py-0.5 text-xs font-mono ${scoreClassName(hit.score)}`}
                      title={t.score}
                    >
                      {hit.score}
                    </span>
                  ) : null}
                  <span
                    className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted"
                    data-testid="hit-similarity"
                  >
                    {t.searchSimilarity}: {hit.similarity.toFixed(3)}
                  </span>
                </div>
              </div>

              <p className="mt-1 text-xs text-ink-muted">
                {hit.source_name ?? "—"} · {formatDateTime(hit.published_at, lang)}
              </p>

              {body ? <p className="mt-2 line-clamp-3 text-sm text-ink/90">{body}</p> : null}

              {tags.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <span
                      key={`${hit.document_id}-${tag}`}
                      className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
