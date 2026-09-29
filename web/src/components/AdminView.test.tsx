import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminView } from "./AdminView";
import { messages, type Messages } from "../i18n";

const ADMIN_KEY_STORAGE = "humanpulse.adminApiKey";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const sources = [
  {
    id: 1,
    name: "Source One",
    kind: "rss",
    url: "https://a.example/feed",
    tier: 1,
    cadence_minutes: 60,
    enabled: true,
    license_note: null,
    last_run_at: "2026-09-27T06:00:00Z",
    last_status: "ok",
    consecutive_failures: 0,
  },
  {
    id: 2,
    name: "Source Two",
    kind: "gdelt",
    url: "https://b.example",
    tier: 2,
    cadence_minutes: 120,
    enabled: false,
    license_note: null,
    last_run_at: null,
    last_status: null,
    consecutive_failures: 3,
  },
];

type Route = (url: string, init: RequestInit | undefined) => Response | undefined;

function stubFetch(route: Route) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    return Promise.resolve(route(url, init) ?? jsonResponse({ detail: "not found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderView(t: Messages) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AdminView t={t} lang="zh" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("AdminView", () => {
  it("没有 API Key 时渲染数据源并提示缺少 Key，且不查询管理接口", async () => {
    const fetchMock = stubFetch((url) => {
      if (url.includes("/api/v1/sources")) return jsonResponse(sources);
      return undefined;
    });
    const t = messages.zh;
    renderView(t);

    expect(await screen.findByText("Source One")).toBeInTheDocument();
    expect(screen.getByText("Source Two")).toBeInTheDocument();
    expect(screen.getByText(t.adminKeyMissing)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).includes("/api/v1/admin/runs")),
    ).toBe(false);
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).includes("/api/v1/admin/usage")),
    ).toBe(false);
  });

  it("有 API Key 时点击停用会 PATCH 数据源并带上 x-api-key", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const fetchMock = stubFetch((url) => {
      if (url.includes("/api/v1/admin/runs")) return jsonResponse([]);
      if (url.includes("/api/v1/admin/usage")) return jsonResponse([]);
      if (/\/api\/v1\/sources\/1$/.test(url)) {
        return jsonResponse({ ...sources[0], enabled: false });
      }
      if (url.includes("/api/v1/sources")) return jsonResponse(sources);
      return undefined;
    });
    const t = messages.zh;
    renderView(t);

    await screen.findByText("Source One");
    fireEvent.click(screen.getAllByText(t.adminSourceDisable)[0]);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).includes("/api/v1/sources/1") && init?.method === "PATCH",
        ),
      ).toBe(true);
    });

    const patchCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/api/v1/sources/1") && init?.method === "PATCH",
    );
    const headers = patchCall?.[1]?.headers as Record<string, string> | undefined;
    expect(headers?.["x-api-key"]).toBe("k");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ enabled: false });
  });

  it("有 API Key 时点击采集一轮会 POST 并把 stats 渲染出来", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const stats = { sources_run: 3, items_new: 5 };
    const fetchMock = stubFetch((url) => {
      if (url.includes("/api/v1/admin/jobs/collect/run")) {
        return jsonResponse({ job: "collect", stats });
      }
      if (url.includes("/api/v1/admin/runs")) return jsonResponse([]);
      if (url.includes("/api/v1/admin/usage")) return jsonResponse([]);
      if (url.includes("/api/v1/sources")) return jsonResponse(sources);
      return undefined;
    });
    const t = messages.zh;
    renderView(t);

    await screen.findByText("Source One");
    fireEvent.click(screen.getByText(t.adminRunCollect));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/api/v1/admin/jobs/collect/run?force=true"),
        ),
      ).toBe(true);
    });

    const collectCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/api/v1/admin/jobs/collect/run?force=true"),
    );
    expect(collectCall?.[1]?.method).toBe("POST");
    expect(await screen.findByText(/"sources_run": 3/)).toBeInTheDocument();
    expect(screen.getByText(t.adminJobResult)).toBeInTheDocument();
  });
});
