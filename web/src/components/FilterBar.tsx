import type { Messages } from "../i18n";

export interface FeedFilters {
  lang: string;
  kind: string;
  minScore: number;
  q: string;
  /** Signal：只看相对新颖（服务端按 band=high 过滤，不在前端筛当前页） */
  noveltyOnly: boolean;
}

export const emptyFilters: FeedFilters = {
  lang: "",
  kind: "",
  minScore: 0,
  q: "",
  noveltyOnly: false,
};

interface FilterBarProps {
  t: Messages;
  filters: FeedFilters;
  onChange: (next: FeedFilters) => void;
}

const selectClass =
  "rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink focus:border-accent focus:outline-none";

export function FilterBar({ t, filters, onChange }: FilterBarProps) {
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => event.preventDefault()}
      aria-label={t.feedTitle}
    >
      <select
        className={selectClass}
        value={filters.lang}
        aria-label={t.filterLanguage}
        onChange={(event) => onChange({ ...filters, lang: event.target.value })}
      >
        <option value="">{t.filterLanguage}: {t.optionAll}</option>
        <option value="zh">{t.optionZh}</option>
        <option value="en">{t.optionEn}</option>
      </select>

      <select
        className={selectClass}
        value={filters.kind}
        aria-label={t.filterKind}
        onChange={(event) => onChange({ ...filters, kind: event.target.value })}
      >
        <option value="">{t.filterKind}: {t.optionAll}</option>
        <option value="news">{t.kindNews}</option>
        <option value="report">{t.kindReport}</option>
        <option value="manual">{t.kindManual}</option>
      </select>

      <select
        className={selectClass}
        value={filters.minScore}
        aria-label={t.filterMinScore}
        onChange={(event) => onChange({ ...filters, minScore: Number(event.target.value) })}
      >
        <option value={0}>{t.filterMinScore}: {t.filterScoreAny}</option>
        <option value={20}>{t.filterMinScore}: 20+</option>
        <option value={40}>{t.filterMinScore}: 40+</option>
        <option value={60}>{t.filterMinScore}: 60+</option>
      </select>

      <input
        className="min-w-[12rem] flex-1 rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        type="search"
        value={filters.q}
        placeholder={t.filterSearchPlaceholder}
        aria-label={t.filterSearch}
        onChange={(event) => onChange({ ...filters, q: event.target.value })}
      />

      <label className="flex items-center gap-2 text-sm text-ink-muted">
        <input
          type="checkbox"
          className="rounded border-line"
          checked={filters.noveltyOnly}
          onChange={(event) => onChange({ ...filters, noveltyOnly: event.target.checked })}
        />
        {t.noveltyFilterOnly}
      </label>

      <button
        type="button"
        className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-muted transition hover:border-accent hover:text-accent"
        onClick={() => onChange(emptyFilters)}
      >
        {t.filterReset}
      </button>
    </form>
  );
}
