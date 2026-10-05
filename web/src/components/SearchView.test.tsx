import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { messages, type Messages } from "../i18n";
import { SearchView } from "./SearchView";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** 记录每次请求的完整 URL，便于断言查询参数。 */
function stubFetch(handler: (url: string) => Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      return Promise.resolve(handler(url));
    }),
  );
  return calls;
}

/** 提交查询：在输入框里改写值并点击搜索按钮。 */
function submitQuery(value: string, t: Messages) {
  fireEvent.change(screen.getByTestId("search-input"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: t.searchTitle }));
}

const hit = {
  document_id: 42,
  title: "Hormuz shipping risk",
  url: "https://example.com/a",
  source_name: "Example News",
  language: "en",
  published_at: "2026-09-27T09:00:00Z",
  score: 88,
  summary_zh: "中文摘要内容",
  summary_en: "English summary body",
  tags: ["shipping", "risk"],
  cluster_id: 5,
  similarity: 0.8123,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SearchView", () => {
  it("少于 2 个字符提交时不发搜索请求，并显示太短提示", async () => {
    const calls = stubFetch(() => jsonResponse([]));
    renderWithClient(<SearchView lang="en" t={messages.en} />);

    submitQuery("a", messages.en);

    expect(await screen.findByText(messages.en.searchTooShort)).toBeInTheDocument();
    expect(calls.filter((url) => url.includes("/api/v1/search"))).toHaveLength(0);
  });

  it("提交关键词后渲染标题与相似度，请求带 q 与 limit", async () => {
    const calls = stubFetch(() => jsonResponse([hit]));
    renderWithClient(<SearchView lang="en" t={messages.en} />);

    submitQuery("shipping risk", messages.en);

    expect(await screen.findByText("Hormuz shipping risk")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Hormuz shipping risk" })).toHaveAttribute(
      "href",
      "#/d/42",
    );
    expect(screen.getByTestId("hit-similarity")).toHaveTextContent("0.812");
    expect(screen.getByText("English summary body")).toBeInTheDocument();

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    const target = calls.find((url) => url.includes("/api/v1/search"));
    expect(target).toBeDefined();
    const decoded = decodeURIComponent((target ?? "").replace(/\+/g, " "));
    expect(decoded).toContain("q=shipping risk");
    expect(decoded).toContain("limit=20");
  });

  it("返回空数组时显示空态", async () => {
    stubFetch(() => jsonResponse([]));
    renderWithClient(<SearchView lang="zh" t={messages.zh} />);

    submitQuery("霍尔木兹", messages.zh);

    expect(await screen.findByText(messages.zh.searchEmpty)).toBeInTheDocument();
  });

  it("接口 500 时显示错误提示且不崩", async () => {
    stubFetch(() => jsonResponse({ detail: "boom" }, 500));
    renderWithClient(<SearchView lang="en" t={messages.en} />);

    submitQuery("climate", messages.en);

    expect(await screen.findByText(messages.en.errorFeed)).toBeInTheDocument();
  });
});
