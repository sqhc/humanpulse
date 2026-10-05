import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BriefView } from "./BriefView";
import { messages } from "../i18n";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const brief = {
  id: 3,
  kind: "daily",
  period_start: "2026-09-26T06:00:00Z",
  period_end: "2026-09-27T06:00:00Z",
  language: "bilingual",
  title: "全球观察日报",
  markdown: "# x",
  structured: {
    title_zh: "全球观察日报（2026-09-27）",
    title_en: "Global brief (2026-09-27)",
    overview_zh: "当天概述",
    overview_en: "Overview",
    sections: [
      {
        key: "conflict",
        heading_zh: "冲突与安全",
        heading_en: "Conflict & security",
        bullets_zh: ["要点一（来源A）"],
        bullets_en: ["Bullet one (Source A)"],
      },
    ],
  },
  model: "deepseek-v4-pro",
  created_at: "2026-09-27T06:00:00Z",
  item_count: 12,
};

function renderView(lang: "zh" | "en") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BriefView lang={lang} t={messages[lang]} />
    </QueryClientProvider>,
  );
}

/** 现有 mock 对所有 URL 返回同一份 body；这里按 URL 分流，brief 与 storyboard 各自可控。 */
function stubFetch(storyboard: () => Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("storyboard")) {
        return storyboard();
      }
      return Promise.resolve(jsonResponse(brief));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BriefView", () => {
  it("渲染中文日报的分组与要点", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(brief))));
    renderView("zh");

    expect(await screen.findByText("全球观察日报（2026-09-27）")).toBeInTheDocument();
    expect(screen.getByText("冲突与安全")).toBeInTheDocument();
    expect(screen.getByText("要点一（来源A）")).toBeInTheDocument();
    expect(screen.getByText(/12/)).toBeInTheDocument();
  });

  it("英文界面用英文标题与要点", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(brief))));
    renderView("en");

    expect(await screen.findByText("Global brief (2026-09-27)")).toBeInTheDocument();
    expect(screen.getByText("Bullet one (Source A)")).toBeInTheDocument();
  });

  it("还没有日报时给出空态", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ detail: "还没有生成任何简报" }, 404))),
    );
    renderView("zh");

    expect(await screen.findByText(/还没有生成/)).toBeInTheDocument();
  });

  it("有简报时渲染脚本 / 字幕下载链接，并带上当前语言", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ scene_count: 3, total_seconds: 42 })));
    renderView("zh");

    const scriptLink = await screen.findByTestId("brief-script-link");
    expect(scriptLink.getAttribute("href")).toContain("/storyboard");
    expect(scriptLink.getAttribute("href")).toContain("language=zh");
    expect(scriptLink).toHaveAttribute("download");

    const srtLink = screen.getByTestId("brief-srt-link");
    expect(srtLink.getAttribute("href")).toContain("/subtitles.srt");
    expect(srtLink.getAttribute("href")).toContain("language=zh");
    expect(srtLink).toHaveAttribute("download");

    // 等 storyboard 请求收尾，避免测试结束后仍有未决状态更新
    await screen.findByTestId("brief-script-metrics");
  });

  it("英文界面链接使用 language=en", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ scene_count: 3, total_seconds: 42 })));
    renderView("en");

    const scriptLink = await screen.findByTestId("brief-script-link");
    expect(scriptLink.getAttribute("href")).toContain("language=en");
    expect(screen.getByTestId("brief-srt-link").getAttribute("href")).toContain("language=en");

    await screen.findByTestId("brief-script-metrics");
  });

  it("显示 storyboard 的场景数与总时长", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ scene_count: 14, total_seconds: 272.3 })));
    renderView("zh");

    const metrics = await screen.findByTestId("brief-script-metrics");
    expect(metrics).toHaveTextContent("14");
    expect(metrics).toHaveTextContent("272.3");
  });

  it("storyboard 请求失败时仍保留链接且不崩溃", async () => {
    stubFetch(() => Promise.resolve(jsonResponse({ detail: "boom" }, 500)));
    renderView("zh");

    expect(await screen.findByTestId("brief-script-link")).toBeInTheDocument();
    expect(screen.getByTestId("brief-srt-link")).toBeInTheDocument();
    expect(screen.queryByTestId("brief-script-metrics")).not.toBeInTheDocument();
  });
});
