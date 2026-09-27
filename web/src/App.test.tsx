import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const NOW = "2026-09-27T12:00:00Z";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function makeDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 1,
    url: "https://example.test/a",
    canonical_url: "https://example.test/a",
    title: "边境冲突第三日：平民伤亡与撤离",
    author: null,
    source_id: 1,
    source_name: "Al Jazeera",
    published_at: NOW,
    fetched_at: NOW,
    language: "zh",
    kind: "news",
    excerpt: "示例正文",
    status: "enriched",
    rejection_reason: null,
    score: 42,
    summary_zh: "中文摘要内容",
    summary_en: "English summary body",
    tags: ["conflict", "humanitarian"],
    regions: ["middle-east"],
    rationale: "涉及冲突与人道影响",
    cluster_id: 1,
    ai_generated: true,
    ...overrides,
  };
}

interface StubOptions {
  documents?: Record<string, unknown>[];
  error?: boolean;
  detail?: Record<string, unknown>;
}

function stubApi(options: StubOptions = {}): void {
  const documents = options.documents ?? [makeDocument()];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (options.error) {
        return Promise.reject(new Error("network down"));
      }
      if (url.includes("/api/v1/health")) {
        return Promise.resolve(
          jsonResponse({
            status: "ok",
            service: "humanpulse-api",
            version: "0.1.0",
            env: "test",
            time: NOW,
          }),
        );
      }
      if (url.includes("/api/v1/ready")) {
        return Promise.resolve(
          jsonResponse({ status: "ready", components: [{ name: "database", ok: true }] }),
        );
      }
      if (/\/api\/v1\/documents\/\d+/.test(url)) {
        return Promise.resolve(
          jsonResponse(options.detail ?? { ...makeDocument(), siblings: [] }),
        );
      }
      if (url.includes("/api/v1/documents")) {
        return Promise.resolve(
          jsonResponse({ items: documents, next_cursor: null, total_returned: documents.length }),
        );
      }
      if (url.includes("/api/v1/clusters")) {
        return Promise.resolve(jsonResponse([]));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }),
  );
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

describe("App", () => {
  it("渲染 Feed 并标注 AI 摘要", async () => {
    stubApi();
    renderApp();

    expect(await screen.findByText("边境冲突第三日：平民伤亡与撤离")).toBeInTheDocument();
    expect(screen.getAllByText(/AI 摘要|AI summary/).length).toBeGreaterThan(0);
    expect(screen.getByText(/42/)).toBeInTheDocument();
  });

  it("后端不可达时给出错误与重试按钮", async () => {
    stubApi({ error: true });
    renderApp();

    expect(
      await screen.findByText(/无法连接后端|Cannot reach the backend/, {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重试|Retry/ })).toBeInTheDocument();
  });

  it("详情路由展示双语摘要与原文链接", async () => {
    stubApi();
    window.location.hash = "#/d/7";
    renderApp();

    expect(await screen.findByText("中文摘要内容")).toBeInTheDocument();
    expect(screen.getByText("English summary body")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /打开原文|Open original/ })).toHaveAttribute(
      "href",
      "https://example.test/a",
    );
  });
});
