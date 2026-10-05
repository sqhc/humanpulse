export type Lang = "zh" | "en";

export interface Messages {
  tagline: string;
  navFeed: string;
  navAbout: string;
  navBriefs: string;
  briefEmpty: string;
  briefPeriod: string;
  briefItems: string;
  briefRaw: string;
  briefNotice: string;
  briefKindDaily: string;
  briefKindWeekly: string;
  navAdmin: string;
  adminKeyTitle: string;
  adminKeyHint: string;
  adminKeySave: string;
  adminKeyClear: string;
  adminKeyMissing: string;
  adminSources: string;
  adminSourcesHint: string;
  adminSourceEnable: string;
  adminSourceDisable: string;
  adminSourceLastRun: string;
  adminSourceFailures: string;
  adminSourceStatus: string;
  adminJobs: string;
  adminJobsHint: string;
  adminRunCollect: string;
  adminRunProcess: string;
  adminRunBriefDaily: string;
  adminRunBriefWeekly: string;
  adminForce: string;
  adminRunning: string;
  adminJobResult: string;
  adminRuns: string;
  adminUsage: string;
  adminEmpty: string;
  adminRefresh: string;
  adminSrcMeta: string;
  adminSeen: string;
  adminNew: string;
  adminRejected: string;
  adminCalls: string;
  adminTokensIn: string;
  adminTokensOut: string;
  adminCost: string;
  adminCandidatesTitle: string;
  adminCandidatesHint: string;
  adminCandidatesEmpty: string;
  adminCandidatesMerge: string;
  adminCandidatesRemember: string;
  adminCandidatesShared: string;
  adminCandidatesOverlap: string;
  adminCandidatesApplied: string;
  adminCandidatesProblems: string;
  adminCandidatesGroups: string;
  adminCandidatesKeepLeft: string;
  adminCandidatesWroteBack: string;
  briefScript: string;
  briefSubtitles: string;
  briefVideoHint: string;
  adminCandidatesKeepRight: string;
  feedTitle: string;
  aiSummaryNotice: string;
  filterLanguage: string;
  filterKind: string;
  filterMinScore: string;
  filterScoreAny: string;
  filterSearch: string;
  filterSearchPlaceholder: string;
  filterReset: string;
  streamLive: string;
  streamConnecting: string;
  streamOffline: string;
  streamReceived: string;
  navEntities: string;
  entitiesTitle: string;
  entitiesHint: string;
  entitiesSearchPlaceholder: string;
  entitiesOrderMentions: string;
  entitiesOrderRecent: string;
  entitiesEmpty: string;
  entitiesMentions: string;
  entityTimeline: string;
  entityRecent: string;
  entityNoTimeline: string;
  entityAliases: string;
  entityFirstSeen: string;
  entityLastSeen: string;
  entityBack: string;
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
    navBriefs: "日报",
    briefEmpty: "还没有生成日报。用 make brief 或等待 worker 到点自动生成。",
    briefPeriod: "统计区间",
    briefItems: "素材条数",
    briefRaw: "查看 Markdown 原文",
    briefNotice: "日报由大模型依据已筛选记录生成，可能存在错误；请以引用的原文为准。",
    briefKindDaily: "日报",
    briefKindWeekly: "周报",
    navAdmin: "管理台",
    adminKeyTitle: "管理员 API Key",
    adminKeyHint: "只保存在本机浏览器（localStorage），用于触发作业与修改数据源。",
    adminKeySave: "保存",
    adminKeyClear: "清除",
    adminKeyMissing: "请先填写管理员 API Key，写操作会返回 401。",
    adminSources: "数据源",
    adminSourcesHint: "连续失败 3 次会被自动停用（熔断）。",
    adminSourceEnable: "启用",
    adminSourceDisable: "停用",
    adminSourceLastRun: "最近采集",
    adminSourceFailures: "连续失败",
    adminSourceStatus: "状态",
    adminJobs: "手动触发作业",
    adminJobsHint: "采集会真的访问外部站点；处理/简报会真实调用 LLM 并产生费用。",
    adminRunCollect: "采集一轮",
    adminRunProcess: "处理待办",
    adminRunBriefDaily: "生成日报",
    adminRunBriefWeekly: "生成周报",
    adminForce: "强制执行",
    adminRunning: "执行中…",
    adminJobResult: "最近一次作业结果",
    adminRuns: "最近采集批次",
    adminUsage: "LLM 用量（7 天）",
    adminEmpty: "暂无数据。",
    adminRefresh: "刷新",
    adminSrcMeta: "类型 / 层级 / 频率",
    adminSeen: "抓取",
    adminNew: "新增",
    adminRejected: "去重/拒绝",
    adminCalls: "调用",
    adminTokensIn: "输入 token",
    adminTokensOut: "输出 token",
    adminCost: "成本",
    adminCandidatesTitle: "实体候选",
    adminCandidatesHint: "同一实体的不同写法（中/英、简/繁）。确认后立即合并；勾选「同时写回别名表」才会改仓库里的 YAML，否则只改这次数据库。",
    adminCandidatesEmpty: "没有待确认的候选。语料越多，候选越可能出现。",
    adminCandidatesMerge: "合并",
    adminCandidatesRemember: "同时写回别名表",
    adminCandidatesShared: "共同文档",
    adminCandidatesOverlap: "重合度",
    adminCandidatesApplied: "已合并",
    adminCandidatesProblems: "别名表自检问题",
    adminCandidatesGroups: "别名组",
    adminCandidatesKeepLeft: "保留左边的名字",
    adminCandidatesWroteBack: "已写回",
    briefScript: "导出视频脚本",
    briefSubtitles: "导出字幕（SRT）",
    briefVideoHint: "脚本与字幕由已入库的简报生成，不额外调用模型。渲染 MP4 需要 ffmpeg 与 Pillow（见 make video）。",
    adminCandidatesKeepRight: "保留右边的名字",
    feedTitle: "最新记录",
    aiSummaryNotice: "以下摘要与评分由大模型生成并标注，原文链接见详情页。",
    filterLanguage: "语言",
    filterKind: "类型",
    filterMinScore: "最低评分",
    filterScoreAny: "不限",
    filterSearch: "关键词",
    filterSearchPlaceholder: "按标题搜索…",
    filterReset: "重置",
    streamLive: "实时",
    streamConnecting: "连接中",
    streamOffline: "未连接",
    streamReceived: "实时新增",
    navEntities: "实体",
    entitiesTitle: "实体时间线",
    entitiesHint: "按提及次数排序；同一实体的中英文写法目前是两条记录（合并需要别名表）。",
    entitiesSearchPlaceholder: "搜索人名 / 组织 / 地点…",
    entitiesOrderMentions: "按提及次数",
    entitiesOrderRecent: "按最近出现",
    entitiesEmpty: "还没有实体数据。先跑采集与处理，或执行 make backfill-entities。",
    entitiesMentions: "提及",
    entityTimeline: "时间线（按天）",
    entityRecent: "最近提及",
    entityNoTimeline: "该时间窗内没有提及。",
    entityAliases: "别名",
    entityFirstSeen: "首次出现",
    entityLastSeen: "最近出现",
    entityBack: "返回实体列表",
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
    navBriefs: "Daily brief",
    briefEmpty: "No brief has been generated yet. Run make brief, or wait for the worker.",
    briefPeriod: "Period",
    briefItems: "Items",
    briefRaw: "View raw Markdown",
    briefNotice: (
      "The brief is AI-generated from filtered records and may contain errors; always check the linked originals."
    ),
    briefKindDaily: "Daily",
    briefKindWeekly: "Weekly",
    navAdmin: "Admin",
    adminKeyTitle: "Admin API key",
    adminKeyHint: "Stored only in this browser (localStorage); used to trigger jobs and edit sources.",
    adminKeySave: "Save",
    adminKeyClear: "Clear",
    adminKeyMissing: "Enter the admin API key first — write calls return 401 without it.",
    adminSources: "Sources",
    adminSourcesHint: "Three consecutive failures disable a source automatically.",
    adminSourceEnable: "Enable",
    adminSourceDisable: "Disable",
    adminSourceLastRun: "Last run",
    adminSourceFailures: "Failures",
    adminSourceStatus: "Status",
    adminJobs: "Run a job",
    adminJobsHint: "Collect hits real websites; process/brief call the LLM and cost money.",
    adminRunCollect: "Collect once",
    adminRunProcess: "Process pending",
    adminRunBriefDaily: "Generate daily brief",
    adminRunBriefWeekly: "Generate weekly brief",
    adminForce: "Force",
    adminRunning: "Running…",
    adminJobResult: "Last job result",
    adminRuns: "Recent fetch runs",
    adminUsage: "LLM usage (7 days)",
    adminEmpty: "Nothing yet.",
    adminRefresh: "Refresh",
    adminSrcMeta: "Kind / tier / cadence",
    adminSeen: "Seen",
    adminNew: "New",
    adminRejected: "Deduped/rejected",
    adminCalls: "Calls",
    adminTokensIn: "Input tokens",
    adminTokensOut: "Output tokens",
    adminCost: "Cost",
    adminCandidatesTitle: "Entity candidates",
    adminCandidatesHint: "The same entity written differently (zh/en, simplified/traditional). Confirming merges immediately; tick the box to also write the repo YAML, otherwise only this database changes.",
    adminCandidatesEmpty: "No candidates waiting. A larger corpus surfaces more candidates.",
    adminCandidatesMerge: "Merge",
    adminCandidatesRemember: "Also write back to the alias table",
    adminCandidatesShared: "shared docs",
    adminCandidatesOverlap: "overlap",
    adminCandidatesApplied: "merged",
    adminCandidatesProblems: "Alias table problems",
    adminCandidatesGroups: "alias groups",
    adminCandidatesKeepLeft: "Keep the left name",
    adminCandidatesWroteBack: "written back",
    briefScript: "Export video script",
    briefSubtitles: "Export subtitles (SRT)",
    briefVideoHint: "Script and subtitles come from the stored brief; no extra model calls. Rendering MP4 needs ffmpeg + Pillow (see make video).",
    adminCandidatesKeepRight: "Keep the right name",
    feedTitle: "Latest records",
    aiSummaryNotice: "Summaries and scores below are AI-generated and labelled; original links are on the detail page.",
    filterLanguage: "Language",
    filterKind: "Kind",
    filterMinScore: "Min score",
    filterScoreAny: "any",
    filterSearch: "Keyword",
    filterSearchPlaceholder: "Search titles…",
    filterReset: "Reset",
    streamLive: "Live",
    streamConnecting: "Connecting",
    streamOffline: "Offline",
    streamReceived: "Live new",
    navEntities: "Entities",
    entitiesTitle: "Entity timeline",
    entitiesHint: "Sorted by mentions; Chinese and English spellings of the same entity are separate rows (merging needs an alias table).",
    entitiesSearchPlaceholder: "Search person / org / place…",
    entitiesOrderMentions: "By mentions",
    entitiesOrderRecent: "By recency",
    entitiesEmpty: "No entity data yet. Run collection + processing, or make backfill-entities.",
    entitiesMentions: "mentions",
    entityTimeline: "Timeline (per day)",
    entityRecent: "Recent mentions",
    entityNoTimeline: "No mentions in this window.",
    entityAliases: "Aliases",
    entityFirstSeen: "First seen",
    entityLastSeen: "Last seen",
    entityBack: "Back to entities",
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
