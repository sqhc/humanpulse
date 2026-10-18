import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { messages } from "../i18n";
import { CoverageCalendar } from "./CoverageCalendar";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

const t = messages.zh;

describe("CoverageCalendar", () => {
  it("三态渲染：正常/空转/断档，并区分无底账日期", async () => {
    const payload = {
      days: [
        { date: "2026-10-01", collected: 100, enriched: 40, has_data: true }, // normal
        { date: "2026-10-02", collected: 60, enriched: 0, has_data: true }, // idle
        { date: "2026-10-03", collected: 0, enriched: 0, has_data: false }, // gap
      ],
      total_collected: 160,
      total_enriched: 40,
      earliest_ledger_date: "2026-09-27",
      coverage_rate: 2 / 3,
    };
    const calls = stubFetch(() => jsonResponse(payload));

    renderWithClient(<CoverageCalendar lang="zh" t={t} />);

    await screen.findByTestId("coverage-calendar");

    const grid = screen.getByRole("img", { name: t.coverageTitle });
    const cells = grid.querySelectorAll("a");
    expect(cells).toHaveLength(3);
    expect(cells[0].dataset.state).toBe("normal");
    expect(cells[1].dataset.state).toBe("idle");
    expect(cells[2].dataset.state).toBe("gap");

    // 点击某天跳 Feed（带 since/until 参数）
    expect(cells[0].getAttribute("href")).toBe(
      "#/?since=2026-10-01T00:00:00&until=2026-10-01T23:59:59",
    );

    // 数值 hover 摘要显示总数
    expect(screen.getByText(/采集 160 条 · 富化 40 条/)).toBeTruthy();
    expect(calls.some((url) => url.includes("/api/v1/coverage/calendar?days=30"))).toBe(true);
  });

  it("无底账日期：earliest_ledger_date 之前的日期显示 noLedger，不给数字", async () => {
    const payload = {
      days: [
        { date: "2026-09-01", collected: 0, enriched: 0, has_data: false },
        { date: "2026-09-28", collected: 20, enriched: 15, has_data: true },
      ],
      total_collected: 20,
      total_enriched: 15,
      earliest_ledger_date: "2026-09-27",
      coverage_rate: 0.5,
    };
    stubFetch(() => jsonResponse(payload));

    renderWithClient(<CoverageCalendar lang="zh" t={t} />);

    await screen.findByTestId("coverage-calendar");
    const cells = screen.getByRole("img", { name: t.coverageTitle }).querySelectorAll("a");
    expect(cells[0].dataset.state).toBe("noLedger");
    expect(cells[1].dataset.state).toBe("normal");
    // 无底账之日 hover 不显示采集/富化数字
    expect(cells[0].getAttribute("title")).toBe("2026-09-01 · 无底账记录");
  });
});
