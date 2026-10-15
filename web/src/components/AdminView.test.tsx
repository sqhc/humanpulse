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

const ENTITY_CANDIDATES = {
  candidates: [
    {
      kind: "org",
      left: { id: 1, name: "中国", mentions: 30 },
      right: { id: 2, name: "China", mentions: 40 },
      shared_documents: 12,
      jaccard: 0.5,
    },
  ],
  alias_group_count: 3,
  alias_problems: [] as string[],
  scanned_pairs: 120,
};

const ENTITY_APPLY = {
  applied_groups: 1,
  merged: 1,
  promoted: 0,
  moved: 1,
  dropped: 0,
  missing: 0,
  remembered: false,
  alias_file: null as string | null,
  total_groups: 1,
  problems: [] as string[],
};

type Route = (url: string, init: RequestInit | undefined) => Response | undefined;

/** 管理台通用路由：实体候选/合并 + 现有区块所需的空响应。 */
function adminRoutes(candidatesBody: unknown, applyBody: unknown): Route {
  return (url) => {
    if (url.includes("/api/v1/admin/entity-aliases/apply")) return jsonResponse(applyBody);
    if (url.includes("/api/v1/admin/entity-candidates")) return jsonResponse(candidatesBody);
    if (url.includes("/api/v1/admin/runs")) return jsonResponse([]);
    if (url.includes("/api/v1/admin/usage")) return jsonResponse([]);
    if (url.includes("/api/v1/sources")) return jsonResponse(sources);
    return undefined;
  };
}

function applyCallBody(fetchMock: ReturnType<typeof stubFetch>): unknown {
  const call = fetchMock.mock.calls.find(
    ([input, init]) =>
      String(input).includes("/api/v1/admin/entity-aliases/apply") && init?.method === "POST",
  );
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
}

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

  it("没有 API Key 时不查询实体候选", async () => {
    const fetchMock = stubFetch((url) => {
      if (url.includes("/api/v1/sources")) return jsonResponse(sources);
      return undefined;
    });
    renderView(messages.zh);

    await screen.findByText("Source One");
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/api/v1/admin/entity-candidates"),
      ),
    ).toBe(false);
  });

  it("有 API Key 时渲染实体候选，点保留右边会合并左边并带上 remember: false", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const fetchMock = stubFetch(adminRoutes(ENTITY_CANDIDATES, ENTITY_APPLY));
    const t = messages.zh;
    renderView(t);

    expect(await screen.findByText(/中国/)).toBeInTheDocument();
    expect(screen.getByText(/China/)).toBeInTheDocument();
    expect(screen.getByText(/共同文档: 12/)).toBeInTheDocument();
    expect(screen.getByText(/重合度: 0.5/)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`${t.adminCandidatesGroups}: 3`)),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("keep-right-1-2"));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).includes("/api/v1/admin/entity-aliases/apply") &&
            init?.method === "POST",
        ),
      ).toBe(true);
    });

    const body = applyCallBody(fetchMock) as {
      merges: { canonical_id: number; alias_ids: number[] }[];
      remember: boolean;
    };
    expect(body.merges[0]?.canonical_id).toBe(2);
    expect(body.merges[0]?.alias_ids).toEqual([1]);
    expect(body.remember).toBe(false);
  });

  it("勾选写回别名表后合并会带上 remember: true", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const fetchMock = stubFetch(
      adminRoutes(ENTITY_CANDIDATES, { ...ENTITY_APPLY, remembered: true, alias_file: "aliases.yaml" }),
    );
    const t = messages.zh;
    renderView(t);

    await screen.findByText(/中国/);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByTestId("keep-right-1-2"));

    await waitFor(() => {
      expect(applyCallBody(fetchMock)).toBeDefined();
    });

    const body = applyCallBody(fetchMock) as { remember: boolean };
    expect(body.remember).toBe(true);
    expect(await screen.findByText(/（已写回 aliases.yaml）/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("合并成功后显示结果，并在顶部显示别名表自检问题", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const fetchMock = stubFetch(
      adminRoutes(
        { ...ENTITY_CANDIDATES, alias_problems: ["alias 'x' 指向不存在的实体"] },
        { ...ENTITY_APPLY, merged: 2, moved: 5 },
      ),
    );
    renderView(messages.zh);

    expect(await screen.findByText(/别名表自检问题/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("keep-left-1-2"));

    expect(await screen.findByText(new RegExp("已合并: 2 / 5"))).toBeInTheDocument();
    expect(applyCallBody(fetchMock)).toBeDefined();
  });

  it("模型判 merge 时出现一键采纳，并保留提及更多的一方", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    const fetchMock = stubFetch(
      adminRoutes(
        {
          ...ENTITY_CANDIDATES,
          candidates: [
            {
              kind: "org",
              left: { id: 1, name: "中国", mentions: 30 },
              right: { id: 2, name: "China", mentions: 40 },
              shared_documents: 12,
              jaccard: 0.5,
              score: 0.62,
              verdict: "merge",
              confidence: 0.7,
            },
          ],
        },
        ENTITY_APPLY,
      ),
    );
    renderView(messages.zh);

    const adopt = await screen.findByTestId("adopt-1-2");
    fireEvent.click(adopt);

    await waitFor(() => {
      expect(applyCallBody(fetchMock)).toBeDefined();
    });
    const body = applyCallBody(fetchMock) as {
      merges: { canonical_id: number; alias_ids: number[] }[];
    };
    // China(40) 提及多于 中国(30)，保留 China
    expect(body.merges[0]?.canonical_id).toBe(2);
    expect(body.merges[0]?.alias_ids).toEqual([1]);
  });

  it("模型判 review 时不显示一键采纳，只留人工按钮", async () => {
    window.localStorage.setItem(ADMIN_KEY_STORAGE, "k");
    stubFetch(
      adminRoutes(
        {
          ...ENTITY_CANDIDATES,
          candidates: [
            {
              kind: "org",
              left: { id: 1, name: "中国", mentions: 30 },
              right: { id: 2, name: "China", mentions: 40 },
              shared_documents: 12,
              jaccard: 0.5,
              score: 0.3,
              verdict: "review",
              confidence: 0.4,
            },
          ],
        },
        ENTITY_APPLY,
      ),
    );
    renderView(messages.zh);

    await screen.findByText(/中国/);
    // 需要人工判断的候选不该出现「一键采纳」——不能替人做决定
    expect(screen.queryByTestId("adopt-1-2")).toBeNull();
    expect(screen.getByTestId("keep-left-1-2")).toBeInTheDocument();
    expect(screen.getByTestId("keep-right-1-2")).toBeInTheDocument();
  });
});
