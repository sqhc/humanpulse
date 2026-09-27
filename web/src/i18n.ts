export type Lang = "zh" | "en";

export interface Messages {
  tagline: string;
  statusTitle: string;
  statusLoading: string;
  statusOk: string;
  statusDegraded: string;
  statusUnreachable: string;
  statusHint: string;
  apiVersion: string;
  roadmapTitle: string;
  phases: { id: string; title: string; detail: string; state: string }[];
  policyTitle: string;
  policyPoints: string[];
  footer: string;
  repo: string;
}

export const messages: Record<Lang, Messages> = {
  zh: {
    tagline: "多源采集 · AI 双语摘要 · 全球观察简报",
    statusTitle: "后端状态",
    statusLoading: "检查中…",
    statusOk: "运行正常",
    statusDegraded: "依赖异常（数据库未就绪）",
    statusUnreachable: "无法连接后端",
    statusHint: "本地可用 make dev 启动 db + api + worker。",
    apiVersion: "API 版本",
    roadmapTitle: "路线图",
    phases: [
      { id: "Phase 0", title: "骨架与仓库", detail: "目录结构、CI、compose、ADR、GitHub 私有仓库", state: "进行中" },
      { id: "Phase 1", title: "核心闭环", detail: "RSS/GDELT/手动上传、SimHash + DeepSeek 摘要、向量去重、Feed", state: "待开始" },
      { id: "Phase 2", title: "简报与上线", detail: "日报/周报、管理台、更多源、SSE、VPS 部署", state: "待开始" },
      { id: "Phase 3", title: "扩展", detail: "视频简报、移动端、实体时间线、语义搜索、深度调查 agent", state: "待开始" },
    ],
    policyTitle: "数据与合规",
    policyPoints: [
      "只采集公开内容，遵守 robots.txt、站点条款与 API 配额",
      "默认只存元数据 + 短引用 + 摘要，不对外提供全文",
      "不使用 X 抓取，不绕过 Cloudflare 等防护",
      "AI 摘要一律标注，平台不做立场性结论",
    ],
    footer: "humanpulse 是信息聚合与观察工具，内容版权归原作者所有。",
    repo: "源码仓库",
  },
  en: {
    tagline: "Multi-source ingestion · bilingual AI briefs · global observation",
    statusTitle: "Backend status",
    statusLoading: "Checking…",
    statusOk: "Operational",
    statusDegraded: "Degraded (database not ready)",
    statusUnreachable: "Backend unreachable",
    statusHint: "Run make dev to start db + api + worker locally.",
    apiVersion: "API version",
    roadmapTitle: "Roadmap",
    phases: [
      { id: "Phase 0", title: "Skeleton & repo", detail: "Layout, CI, compose, ADRs, private GitHub repo", state: "in progress" },
      { id: "Phase 1", title: "Core loop", detail: "RSS/GDELT/manual upload, SimHash + DeepSeek summaries, vector dedup, feed", state: "planned" },
      { id: "Phase 2", title: "Briefs & deploy", detail: "Daily/weekly briefs, admin, more sources, SSE, VPS deploy", state: "planned" },
      { id: "Phase 3", title: "Expansion", detail: "Video briefs, mobile, entity timeline, semantic search, deep-research agent", state: "planned" },
    ],
    policyTitle: "Data & compliance",
    policyPoints: [
      "Public sources only; respects robots.txt, site terms and API quotas",
      "Stores metadata + short quotes + summaries; never serves full text",
      "No X scraping, no bot-protection bypass",
      "AI summaries are always labelled; the platform takes no editorial stance",
    ],
    footer: "humanpulse is an aggregation and observation tool. Content rights belong to original publishers.",
    repo: "Source repository",
  },
};
