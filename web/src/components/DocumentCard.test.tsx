import type { DocumentOut } from "@humanpulse/api-client";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messages } from "../i18n";
import { DocumentCard } from "./DocumentCard";

function makeDocument(overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: 1,
    url: "https://example.test/a",
    canonical_url: "https://example.test/a",
    title: "Ceasefire talks resume in the border region",
    fetched_at: "2026-09-27T12:00:00Z",
    kind: "news",
    status: "enriched",
    score: 55,
    summary_zh: "中文摘要",
    summary_en: "English summary",
    tags: ["conflict"],
    regions: [],
    cluster_id: 1,
    source_name: "Al Jazeera",
    ai_generated: true,
    ...overrides,
  } as DocumentOut;
}

describe("DocumentCard", () => {
  it("展示标题、来源、评分与标签", () => {
    render(<DocumentCard doc={makeDocument()} lang="en" t={messages.en} />);

    expect(screen.getByText("Ceasefire talks resume in the border region")).toBeInTheDocument();
    expect(screen.getByText(/Al Jazeera/)).toBeInTheDocument();
    expect(screen.getByText("55")).toBeInTheDocument();
    expect(screen.getByText("conflict")).toBeInTheDocument();
    expect(screen.getByText("AI summary")).toBeInTheDocument();
  });

  it("仅标题的条目标出标记且不再重复展示标签", () => {
    render(
      <DocumentCard
        doc={makeDocument({ tags: ["conflict", "headline-only"] })}
        lang="en"
        t={messages.en}
      />,
    );

    expect(screen.getByText(/headline only/)).toBeInTheDocument();
    expect(screen.queryByText("headline-only")).not.toBeInTheDocument();
  });

  it("中文界面优先展示中文摘要", () => {
    render(<DocumentCard doc={makeDocument()} lang="zh" t={messages.zh} />);
    expect(screen.getByText("中文摘要")).toBeInTheDocument();
  });
});

describe("DocumentCard novelty badge", () => {
  it("band=high 显示「相对新颖」，band=covered 显示「近期已覆盖」", () => {
    const { unmount } = render(
      <DocumentCard doc={makeDocument({ band: "high", percentile: 88 })} lang="zh" t={messages.zh} />,
    );
    expect(screen.getByTestId("novelty-badge")).toHaveTextContent("相对新颖");
    unmount();

    render(
      <DocumentCard
        doc={makeDocument({ band: "covered", percentile: 12 })}
        lang="zh"
        t={messages.zh}
      />,
    );
    expect(screen.getByTestId("novelty-badge")).toHaveTextContent("近期已覆盖");
  });

  it("band=mid 或缺失时不渲染徽标", () => {
    const { unmount } = render(
      <DocumentCard doc={makeDocument({ band: "mid" })} lang="zh" t={messages.zh} />,
    );
    expect(screen.queryByTestId("novelty-badge")).toBeNull();
    unmount();

    render(<DocumentCard doc={makeDocument()} lang="zh" t={messages.zh} />);
    expect(screen.queryByTestId("novelty-badge")).toBeNull();
  });

  it("cohort fallback 或 percentile<1 时不显示「比 N% 更新」，只留 band 与相对口径说明", () => {
    render(
      <DocumentCard
        doc={makeDocument({ band: "high", percentile: 100 })}
        cohortFallback
        lang="zh"
        t={messages.zh}
      />,
    );
    const badge = screen.getByTestId("novelty-badge");
    expect(badge).not.toHaveAttribute("title", expect.stringContaining("比 100%"));
    expect(badge).toHaveAttribute("title", expect.stringContaining("相对切分"));
  });

  it("percentile 有效时悬停带百分位", () => {
    render(
      <DocumentCard
        doc={makeDocument({ band: "high", percentile: 88 })}
        lang="zh"
        t={messages.zh}
      />,
    );
    expect(screen.getByTestId("novelty-badge")).toHaveAttribute(
      "title",
      expect.stringContaining("比 88%"),
    );
  });
});
