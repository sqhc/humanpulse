import type { EntityOut } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import type { Lang, Messages } from "../i18n";
import { createApiClient } from "../lib/api";
import { formatDateTime } from "../lib/format";

/** 实体列表一次拉取的上限；Phase 1 还没有分页接口。 */
const LIST_LIMIT = 50;

type EntityOrder = "mentions" | "recent";

interface EntitiesViewProps {
  lang: Lang;
  t: Messages;
}

export function EntitiesView({ lang, t }: EntitiesViewProps) {
  const api = useMemo(() => createApiClient(), []);
  const [search, setSearch] = useState("");
  const [order, setOrder] = useState<EntityOrder>("mentions");
  const q = search.trim();

  const entities = useQuery({
    queryKey: ["entities", { q, order }],
    queryFn: ({ signal }) =>
      api.listEntities({ q: q || undefined, order, limit: LIST_LIMIT }, { signal }),
  });

  const items: EntityOut[] = entities.data ?? [];

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold text-ink">{t.entitiesTitle}</h2>
        <p className="text-xs text-ink-muted">{t.entitiesHint}</p>
      </header>

      <div className="flex flex-wrap gap-2">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t.entitiesSearchPlaceholder}
          className="min-w-0 flex-1 rounded-md border border-line bg-surface-muted/40 px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        />
        <select
          value={order}
          onChange={(event) => setOrder(event.target.value as EntityOrder)}
          className="rounded-md border border-line bg-surface-muted/40 px-3 py-1.5 text-sm text-ink focus:border-accent focus:outline-none"
        >
          <option value="mentions">{t.entitiesOrderMentions}</option>
          <option value="recent">{t.entitiesOrderRecent}</option>
        </select>
      </div>

      {entities.isPending ? <p className="text-sm text-ink-muted">{t.loading}</p> : null}

      {entities.isError ? (
        <p className="rounded-xl border border-red-400/40 bg-red-500/5 p-4 text-sm text-red-200">
          {t.errorFeed}
        </p>
      ) : null}

      {!entities.isPending && !entities.isError && items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface-muted/40 p-4 text-sm text-ink-muted">
          {t.entitiesEmpty}
        </p>
      ) : null}

      <ul className="space-y-2">
        {items.map((entity) => (
          <li
            key={entity.id}
            className="rounded-xl border border-line bg-surface-muted/40 p-3"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <a
                className="text-sm font-medium text-ink hover:text-accent"
                href={`#/entities/${entity.id}`}
              >
                {entity.name}
              </a>
              <span className="rounded bg-line/40 px-2 py-0.5 text-[11px] text-ink-muted">
                {entity.kind}
              </span>
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {t.entitiesMentions}: {entity.mention_count} · {t.entityLastSeen}:{" "}
              {formatDateTime(entity.last_seen_at, lang)}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
