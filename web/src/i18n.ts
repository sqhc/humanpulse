export type Lang = "zh" | "en";

export interface Messages {
  tagline: string;
  navFeed: string;
  navAbout: string;
  feedTitle: string;
  aiSummaryNotice: string;
  filterLanguage: string;
  filterKind: string;
  filterMinScore: string;
  filterScoreAny: string;
  filterSearch: string;
  filterSearchPlaceholder: string;
  filterReset: string;
  optionAll: string;
  optionZh: string;
  optionEn: string;
  kindNews: string;
  kindReport: string;
  kindManual: string;
  loading: string;
  emptyFeed: string;
  errorFeed: string;
  retry: string;
  loadMore: string;
  noMore: string;
  aiSummary: string;
  headlineOnly: string;
  score: string;
  rationale: string;
  sameEvent: string;
  noSiblings: string;
  backToFeed: string;
  openOriginal: string;
  source: string;
  published: string;
  notFound: string;
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
    tagline: "多源采集 · AI 双语摘要 · 全球观察",
    navFeed: "Feed",
    navAbout: "关于与方法",
    feedTitle: "最新记录",
    aiSummaryNotice: "以下摘要与评分由大模型生成并标注，原文链接见详情页。",
    filterLanguage: "语言",
    filterKind: "类型",
    filterMinScore: "最低评分",
    filterScoreAny: "不限",
    filterSearch: "关键词",
    filterSearchPlaceholder: "按标题搜索…",
    filterReset: "重置",
    optionAll: "全部",
    optionZh: "中文",
    optionEn: "英文",
    kindNews: "新闻",
    kindReport: "报告",
    kindManual: "手动上传",
    loading: "加载中…",
    emptyFeed: "没有匹配的内容。可以放宽筛选条件，或先用 make dev + make collect-once 采集一轮。",
    errorFeed: "无法连接后端，或接口返回了错误。",
    retry: "重试",
    loadMore: "加载更多",
    noMore: "已经到底了",
    aiSummary: "AI 摘要",
    headlineOnly: "仅标题",
    score: "评分",
    rationale: "评分理由",
    sameEvent: "同一事件的其他报道",
    noSiblings: "暂无其它来源的报道。",
    backToFeed: "返回 Feed",
    openOriginal: "打开原文",
    source: "来源",
    published: "发布",
    notFound: "找不到这条记录。",
    statusTitle: "后端状态",
    statusLoading: "检查中…",
    statusOk: "运行正常",
    statusDegraded: "依赖异常（数据库未就绪）",
    statusUnreachable: "无法连接后端",
    statusHint: "本地可用 make dev 启动 db + api + worker。",
    apiVersion: "API 版本",
    roadmapTitle: "路线图",
    phases: [
      { id: "Phase 0", title: "骨架与仓库", detail: "目录结构、CI、compose、ADR、GitHub 私有仓库", state: "已完成" },
      { id: "Phase 1", title: "核心闭环", detail: "RSS/GDELT/手动上传、SimHash + DeepSeek 摘要、向量去重与聚类、读取接口与 Feed", state: "进行中" },
      { id: "Phase 2", title: "简报与上线", detail: "日报/周报、管理台、更多源、SSE、VPS 部署", state: "待开始" },
      { id: "Phase 3", title: "扩展", detail: "视频简报、移动端、实体时间线、语义搜索、深度调查 agent", state: "待开始" },
    ],
    policyTitle: "数据与合规",
    policyPoints: [
      "只采集公开内容，遵守 robots.txt、站点条款与 API 配额",
      "默认只存元数据 + 短引用 + 摘要，不对外提供全文",
      "不使用 X 抓取，不绕过 Cloudflare 等防护（被拦的源直接停用）",
      "AI 摘要一律标注，平台不做立场性结论",
    ],
    footer: "humanpulse 是信息聚合与观察工具，内容版权归原作者所有；摘要由大模型生成，请以原文为准。",
    repo: "源码仓库",
  },
  en: {
    tagline: "Multi-source ingestion · bilingual AI briefs · global observation",
    navFeed: "Feed",
    navAbout: "About & method",
    feedTitle: "Latest records",
    aiSummaryNotice: "Summaries and scores below are AI-generated and labelled; original links are on the detail page.",
    filterLanguage: "Language",
    filterKind: "Kind",
    filterMinScore: "Min score",
    filterScoreAny: "any",
    filterSearch: "Keyword",
    filterSearchPlaceholder: "Search titles…",
    filterReset: "Reset",
    optionAll: "all",
    optionZh: "Chinese",
    optionEn: "English",
    kindNews: "news",
    kindReport: "report",
    kindManual: "manual upload",
    loading: "Loading…",
    emptyFeed: "Nothing matches. Loosen the filters, or run make dev + make collect-once to ingest a first batch.",
    errorFeed: "Cannot reach the backend, or the API returned an error.",
    retry: "Retry",
    loadMore: "Load more",
    noMore: "End of feed",
    aiSummary: "AI summary",
    headlineOnly: "headline only",
    score: "score",
    rationale: "Why this score",
    sameEvent: "Other coverage of the same event",
    noSiblings: "No other sources yet.",
    backToFeed: "Back to feed",
    openOriginal: "Open original",
    source: "Source",
    published: "Published",
    notFound: "This record was not found.",
    statusTitle: "Backend status",
    statusLoading: "Checking…",
    statusOk: "Operational",
    statusDegraded: "Degraded (database not ready)",
    statusUnreachable: "Backend unreachable",
    statusHint: "Run make dev to start db + api + worker locally.",
    apiVersion: "API version",
    roadmapTitle: "Roadmap",
    phases: [
      { id: "Phase 0", title: "Skeleton & repo", detail: "Layout, CI, compose, ADRs, private GitHub repo", state: "done" },
      { id: "Phase 1", title: "Core loop", detail: "RSS/GDELT/manual upload, SimHash + DeepSeek summaries, vector dedup/clustering, read API and feed", state: "in progress" },
      { id: "Phase 2", title: "Briefs & deploy", detail: "Daily/weekly briefs, admin console, more sources, SSE, VPS deploy", state: "planned" },
      { id: "Phase 3", title: "Expansion", detail: "Video briefs, mobile, entity timeline, semantic search, deep-research agent", state: "planned" },
    ],
    policyTitle: "Data & compliance",
    policyPoints: [
      "Public sources only; respects robots.txt, site terms and API quotas",
      "Stores metadata + short quotes + summaries; never serves full text",
      "No X scraping, no bot-protection bypass — blocked sources are disabled instead",
      "AI summaries are always labelled; the platform takes no editorial stance",
    ],
    footer: "humanpulse is an aggregation and observation tool. Content rights belong to original publishers; summaries are AI-generated, always check the original.",
    repo: "Source repository",
  },
};
