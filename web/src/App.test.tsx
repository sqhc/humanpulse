import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
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
});

describe("App", () => {
  it("显示后端正常状态与版本号", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/health")) {
          return Promise.resolve(
            jsonResponse({
              status: "ok",
              service: "humanpulse-api",
              version: "0.1.0",
              env: "test",
              time: "2026-01-01T00:00:00Z",
            }),
          );
        }
        return Promise.resolve(
          jsonResponse({ status: "ready", components: [{ name: "database", ok: true }] }),
        );
      }),
    );

    renderApp();

    expect(await screen.findByText(/0.1.0/)).toBeInTheDocument();
    expect(await screen.findByTestId("status-label")).toBeInTheDocument();
  });

  it("后端不可达时给出提示", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    renderApp();

    expect(
      await screen.findByText(/无法连接后端|Backend unreachable/, {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
