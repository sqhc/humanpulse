import type { Messages } from "../i18n";

interface RoadmapProps {
  t: Messages;
}

export function Roadmap({ t }: RoadmapProps) {
  return (
    <section className="rounded-xl border border-line bg-surface-muted/40 p-5">
      <h2 className="text-sm font-medium text-ink-muted">{t.roadmapTitle}</h2>
      <ul className="mt-3 space-y-3">
        {t.phases.map((phase) => (
          <li key={phase.id} className="border-l-2 border-line pl-3">
            <p className="text-sm font-semibold text-ink">
              <span className="font-mono text-accent">{phase.id}</span> · {phase.title}
            </p>
            <p className="text-sm text-ink-muted">{phase.detail}</p>
            <p className="mt-0.5 text-xs uppercase tracking-wide text-ink-muted">{phase.state}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
