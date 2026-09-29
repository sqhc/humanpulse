import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { messages } from "../i18n";
import { EntitiesView } from "./EntitiesView";
import { EntityDetailView } from "./EntityDetailView";

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

const acme = {
  id: 1,
  name: "Acme Corp",
  kind: "org",
  aliases: ["Acme", "ACME 公司"],
  mention_count: 42,
  first_seen_at: "2026-09-01T08:00:00Z",
  last_seen_at: "2026-09-27T10:00:00Z",
};

const jane = {
  id: 2,
  name: "Jane Doe",
  kind: "person",
  aliases: [],
  mention_count: 13,
  first_seen_at: "2026-09-10T08:00:00Z",
  last_seen_at: "2026-09-25T10:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EntitiesView", () => {
  it("渲染实体名、类型与提及次数，请求带上 limit", async () => {
    const calls = stubFetch(() => jsonResponse([acme, jane]));
    renderWithClient(<EntitiesView lang="zh" t={messages.zh} />);

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText(/42/)).toBeInTheDocument();
    expect(screen.getByText(/13/)).toBeInTheDocument();

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(calls[0]).toContain("/api/v1/entities");
    expect(calls[0]).toContain("limit=");
  });

  it("搜索输入触发带 q 的新查询", async () => {
    const calls = stubFetch(() => jsonResponse([]));
    renderWithClient(<EntitiesView lang="en" t={messages.en} />);

    await waitFor(() => expect(calls.length).toBe(1));

    fireEvent.change(screen.getByPlaceholderText(messages.en.entitiesSearchPlaceholder), {
      target: { value: "climate" },
    });

    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(calls[1]).toContain("q=climate");
  });
});

describe("EntityDetailView", () => {
  const detail = {
    ...acme,
    timeline: [
      { day: "2026-09-26", count: 2 },
      { day: "2026-09-27", count: 4 },
    ],
    recent: [
      {
        document_id: 42,
        title: "Original report",
        url: "https://example.com/a",
        source_name: "Example News",
        published_at: "2026-09-27T09:00:00Z",
        score: 88,
        cluster_id: 5,
        salience: 0.9,
      },
    ],
  };

  it("渲染时间线条形与最近提及的文档链接", async () => {
    stubFetch(() => jsonResponse(detail));
    renderWithClient(<EntityDetailView id={7} lang="en" t={messages.en} />);

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getAllByTestId("timeline-bar")).toHaveLength(2);
    expect(screen.getByText("Acme 公司", { exact: false })).toBeInTheDocument();

    const link = screen.getByRole("link", { name: "Original report" });
    expect(link).toHaveAttribute("href", "#/d/42");
    expect(screen.getByText(/Example News/)).toBeInTheDocument();
    expect(screen.getByText(/88/)).toBeInTheDocument();
  });

  it("404 时显示未找到与返回链接", async () => {
    stubFetch(() => jsonResponse({ detail: "not found" }, 404));
    renderWithClient(<EntityDetailView id={999} lang="zh" t={messages.zh} />);

    expect(await screen.findByText(messages.zh.notFound)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /返回实体列表/ })).toHaveAttribute(
      "href",
      "#/entities",
    );
  });
});
