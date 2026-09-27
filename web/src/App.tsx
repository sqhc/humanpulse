import { ApiError } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Header } from "./components/Header";
import { PolicyCard } from "./components/PolicyCard";
import { Roadmap } from "./components/Roadmap";
import { StatusCard, type StatusState } from "./components/StatusCard";
import { messages, type Lang } from "./i18n";
import { createApiClient } from "./lib/api";

const REPO_URL = "https://github.com/sqhc/humanpulse";

function detectLang(): Lang {
  const nav = typeof navigator === "undefined" ? "" : navigator.language;
  return nav.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function App() {
  const [lang, setLang] = useState<Lang>(detectLang);
  const t = messages[lang];
  const api = useMemo(() => createApiClient(), []);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health({ signal }),
    // 网络抖动先快速重试一次，仍然失败才显示"无法连接"
    retry: 1,
    retryDelay: 400,
  });

  const ready = useQuery({
    queryKey: ["ready"],
    queryFn: ({ signal }) => api.ready({ signal }),
    retry: 0,
  });

  const state: StatusState = health.isPending
    ? "loading"
    : health.isError
      ? "unreachable"
      : ready.isError && ready.error instanceof ApiError && ready.error.status === 503
        ? "degraded"
        : "ok";

  const errorMessage =
    health.error instanceof ApiError ? `HTTP ${health.error.status}` : undefined;

  return (
    <div className="min-h-screen">
      <Header t={t} lang={lang} onToggleLang={() => setLang(lang === "zh" ? "en" : "zh")} />
      <main className="mx-auto grid max-w-4xl gap-5 px-6 py-8 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <StatusCard
            t={t}
            state={state}
            version={health.data?.version}
            ready={ready.data}
            errorMessage={errorMessage}
          />
        </div>
        <Roadmap t={t} />
        <PolicyCard t={t} />
        <footer className="sm:col-span-2 border-t border-line/70 pt-4 text-sm text-ink-muted">
          <p>{t.footer}</p>
          <p className="mt-1">
            {t.repo}:{" "}
            <a className="text-accent hover:underline" href={REPO_URL} rel="noreferrer noopener">
              sqhc/humanpulse
            </a>
          </p>
        </footer>
      </main>
    </div>
  );
}
