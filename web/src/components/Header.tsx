import type { Lang, Messages } from "../i18n";

interface HeaderProps {
  t: Messages;
  lang: Lang;
  onToggleLang: () => void;
}

export function Header({ t, lang, onToggleLang }: HeaderProps) {
  return (
    <header className="border-b border-line/70 bg-surface-muted/40">
      <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-accent">humanpulse</h1>
          <p className="mt-0.5 text-sm text-ink-muted">{t.tagline}</p>
        </div>
        <button
          type="button"
          onClick={onToggleLang}
          className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-muted transition hover:border-accent hover:text-accent"
          aria-label="switch language"
        >
          {lang === "zh" ? "EN" : "中文"}
        </button>
      </div>
    </header>
  );
}
