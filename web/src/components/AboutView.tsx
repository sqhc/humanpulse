import type { Messages } from "../i18n";
import { PolicyCard } from "./PolicyCard";
import { Roadmap } from "./Roadmap";
import { StatusCard, type StatusState } from "./StatusCard";

interface AboutViewProps {
  t: Messages;
  state: StatusState;
  version?: string;
  errorMessage?: string;
}

export function AboutView({ t, state, version, errorMessage }: AboutViewProps) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <StatusCard t={t} state={state} version={version} errorMessage={errorMessage} />
      </div>
      <Roadmap t={t} />
      <PolicyCard t={t} />
    </div>
  );
}
