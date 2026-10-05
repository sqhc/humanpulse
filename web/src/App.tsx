import { ApiError } from "@humanpulse/api-client";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { AboutView } from "./components/AboutView";
import { AdminView } from "./components/AdminView";
import { BriefView } from "./components/BriefView";
import { DocumentDetailView } from "./components/DocumentDetailView";
import { EntitiesView } from "./components/EntitiesView";
import { EntityDetailView } from "./components/EntityDetailView";
import { FeedView } from "./components/FeedView";
import { Header } from "./components/Header";
import { SearchView } from "./components/SearchView";
import type { StatusState } from "./components/StatusCard";
import { messages, type Lang } from "./i18n";
import { createApiClient } from "./lib/api";
import { useRoute } from "./lib/router";

const REPO_URL = "https://github.com/sqhc/humanpulse";

function detectLang(): Lang {
  const nav = typeof navigator === "undefined" ? "" : navigator.language;
  return nav.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function App() {
  const [lang, setLang] = useState<Lang>(detectLang);
  const t = messages[lang];
  const route = useRoute();
  const api = useMemo(() => createApiClient(), []);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => api.health({ signal }),
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

  const navClass = (active: boolean) =>
    active ? "text-accent" : "text-ink-muted transition hover:text-accent";

  return (
    <div className="min-h-screen">
      <Header t={t} lang={lang} onToggleLang={() => setLang(lang === "zh" ? "en" : "zh")} />
      <nav className="mx-auto flex max-w-4xl gap-5 px-6 pt-4 text-sm">
        <a className={navClass(route.name === "feed")} href="#/">
          {t.navFeed}
        </a>
        <a className={navClass(route.name === "brief")} href="#/briefs">
          {t.navBriefs}
        </a>
        <a className={navClass(route.name === "entities" || route.name === "entity")} href="#/entities">
          {t.navEntities}
        </a>
        <a className={navClass(route.name === "search")} href="#/search">
          {t.navSearch}
        </a>
        <a className={navClass(route.name === "about")} href="#/about">
          {t.navAbout}
        </a>
        <a className={navClass(route.name === "admin")} href="#/admin">
          {t.navAdmin}
        </a>
      </nav>
      <main className="mx-auto max-w-4xl px-6 py-6">
        {route.name === "document" ? (
          <DocumentDetailView id={route.id} lang={lang} t={t} />
        ) : route.name === "brief" ? (
          <BriefView lang={lang} t={t} />
        ) : route.name === "entities" ? (
          <EntitiesView lang={lang} t={t} />
        ) : route.name === "entity" ? (
          <EntityDetailView id={route.id} lang={lang} t={t} />
        ) : route.name === "search" ? (
          <SearchView lang={lang} t={t} />
        ) : route.name === "admin" ? (
          <AdminView t={t} lang={lang} />
        ) : route.name === "about" ? (
          <AboutView
            t={t}
            state={state}
            version={health.data?.version}
            errorMessage={errorMessage}
          />
        ) : (
          <FeedView lang={lang} t={t} />
        )}
      </main>
      <footer className="mx-auto max-w-4xl border-t border-line/70 px-6 py-6 text-sm text-ink-muted">
        <p>{t.footer}</p>
        <p className="mt-1">
          {t.repo}:{" "}
          <a className="text-accent hover:underline" href={REPO_URL} rel="noreferrer noopener">
            sqhc/humanpulse
          </a>
        </p>
      </footer>
    </div>
  );
}
