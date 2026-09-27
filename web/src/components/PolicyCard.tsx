import type { Messages } from "../i18n";

interface PolicyCardProps {
  t: Messages;
}

export function PolicyCard({ t }: PolicyCardProps) {
  return (
    <section className="rounded-xl border border-line bg-surface-muted/40 p-5">
      <h2 className="text-sm font-medium text-ink-muted">{t.policyTitle}</h2>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-muted">
        {t.policyPoints.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
    </section>
  );
}
