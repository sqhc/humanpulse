import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { messages } from "../i18n";
import { PipelineOverview } from "./PipelineOverview";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const sources = [
  { id: 1, name: "Al Jazeera", kind: "rss", url: "https://a.example", tier: 1, cadence_minutes: 60, enabled: true, license_note: null, last_run_at: null, last_status: null, consecutive_failures: 0 },
  { id: 2, name: "BBC World", kind: "rss", url: "https://b.example", tier: 1, cadence_minutes: 30, enabled: true, license_note: null, last_run_at: null, last_status: null, consecutive_failures: 0 },
];

const documents = {
  items: [
    { id: 1, status: "enriched", title: "t1", canonical_url: "https://x", fetched_at: "2026-10-15T00:00:00Z", score: 80, source_name: "Al Jazeera", language: "zh", kind: "news", ai_generated: true, tags: ["conflict"], regions: [], summary_zh: "s", summary_en: "s" },
    { id: 2, status: "pending", title: "t2", canonical_url: "https://y", fetched_at: "2026-10-15T00:00:00Z", score: 50, source_name: "BBC", language: "en", kind: "news", ai_generated: true, tags: [], regions: [], summary_zh: "", summary_en: "" },
  ],
  next_cursor: null,
  total_returned: 2,
};

const brief = {
  id: 19, kind: "weekly", title: "全球观察周报（2026-10-09 ~ 10-16 UTC）", model: "deepseek-v4-pro",
  period_start: "2026-10-09T00:00:00Z", period_end: "2026-10-16T00:00:00Z",
  language: "bilingual", markdown: "", structured: {}, created_at: "2026-10-15T13:31:34Z", item_count: 20,
};

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PipelineOverview lang="zh" t={messages.zh} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PipelineOverview", () => {
  it("渲染 5 阶段横条与判官门禁提示", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/sources")) return jsonResponse(sources);
        if (url.includes("/api/v1/documents")) return jsonResponse(documents);
        if (url.includes("/api/v1/briefs/latest")) return jsonResponse(brief);
        return jsonResponse({});
      }),
    );

    renderView();

    await screen.findByText("2 源 · 2 条");
    expect(screen.getAllByText("采集", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("富化", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("入库", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("判官", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("输出", { exact: false }).length).toBeGreaterThan(0);

    // 判官门禁提示
    expect(screen.getAllByText(/AUC 0\.528/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/projection_enabled=false/).length).toBeGreaterThan(0);
  });

  it("加载中时不崩溃", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    renderView();
    expect(screen.getByText("加载中…")).toBeInTheDocument();
  });
});