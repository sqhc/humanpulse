import type { components, paths } from "./generated/schema";

type JsonOf<T> = T extends { content: { "application/json": infer R } } ? R : never;

export type HealthResponse = JsonOf<paths["/api/v1/health"]["get"]["responses"][200]>;
export type ReadyResponse =
  | JsonOf<paths["/api/v1/ready"]["get"]["responses"][200]>
  | JsonOf<paths["/api/v1/ready"]["get"]["responses"][503]>;

/** 读取端模型：全部从 OpenAPI 生成物里取，接口改动会在类型检查阶段暴露。 */
export type DocumentOut = components["schemas"]["DocumentOut"];
export type DocumentListOut = components["schemas"]["DocumentListOut"];
export type DocumentDetailOut = components["schemas"]["DocumentDetailOut"];
export type ClusterOut = components["schemas"]["ClusterOut"];
export type SourceOut = components["schemas"]["SourceOut"];
export type SourceUpdate = components["schemas"]["SourceUpdate"];
export type FetchRunOut = components["schemas"]["FetchRunOut"];
export type LlmUsageOut = components["schemas"]["LlmUsageOut"];
export type JobResultOut = components["schemas"]["JobResultOut"];

/** 可手动触发的作业名。 */
export type JobName = "collect" | "process" | "brief";
export type BriefOut = components["schemas"]["BriefOut"];
export type BriefListItem = components["schemas"]["BriefListItem"];
export type EntityOut = components["schemas"]["EntityOut"];
export type EntityDetailOut = components["schemas"]["EntityDetailOut"];
export type EntityTimelinePoint = components["schemas"]["EntityTimelinePoint"];
export type EntityMentionOut = components["schemas"]["EntityMentionOut"];
export type EntityCandidateOut = components["schemas"]["EntityCandidateOut"];
export type EntityCandidateListOut = components["schemas"]["EntityCandidateListOut"];
export type EntityAliasApplyIn = components["schemas"]["EntityAliasApplyIn"];
export type EntityAliasApplyOut = components["schemas"]["EntityAliasApplyOut"];
export type SearchHitOut = components["schemas"]["SearchHitOut"];
export type PredictionOut = components["schemas"]["PredictionOut"];
export type PredictionListOut = components["schemas"]["PredictionListOut"];
export type CalibrationOut = components["schemas"]["CalibrationOut"];
export type DocumentNoveltyOut = components["schemas"]["DocumentNoveltyOut"];
export type CoverageCalendarOut = components["schemas"]["CoverageCalendarOut"];
export type CoverageDayOut = components["schemas"]["CoverageDayOut"];

/** 结构化简报内容（由服务端渲染 Markdown，前端按语言取字段）。 */
export interface BriefSection {
  key: string;
  heading_zh: string;
  heading_en: string;
  bullets_zh: string[];
  bullets_en: string[];
}

/** 脉搏短讯：事实一句 + 钩子（简报生成时由同次 LLM 调用产出，前端只读）。 */
export interface PulseCard {
  section_key?: string;
  fact_zh?: string;
  fact_en?: string;
  hook_zh?: string;
  hook_en?: string;
  source_name?: string;
}

export interface BriefContentShape {
  title_zh?: string;
  title_en?: string;
  overview_zh?: string;
  overview_en?: string;
  sections?: BriefSection[];
  closing_zh?: string;
  closing_en?: string;
  pulses?: PulseCard[];
}

/** Feed 查询参数（来自 OpenAPI 的 query 定义）。 */
export type DocumentQuery = NonNullable<
  paths["/api/v1/documents"]["get"]["parameters"]["query"]
>;

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `humanpulse API 返回 ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ClientOptions {
  /** API 基地址；留空表示同源（浏览器下配合反向代理）。 */
  baseUrl?: string;
  /** 自定义 fetch（测试或 SSR 场景）。 */
  fetchFn?: typeof fetch;
  /** 管理员 API Key；只有写操作（上传/作业/源管理）需要。 */
  apiKey?: string;
}

export interface RequestOptions {
  signal?: AbortSignal;
}

type QueryValue = string | number | boolean | null | undefined;

function toQueryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function createClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
  const doFetch = options.fetchFn ?? globalThis.fetch;
  const apiKey = options.apiKey ?? "";

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const resp = await doFetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        accept: "application/json",
        ...(apiKey ? { "x-api-key": apiKey } : {}),
        ...(init.headers ?? {}),
      },
    });
    const text = await resp.text();
    const body: unknown = text ? JSON.parse(text) : null;
    if (!resp.ok) {
      throw new ApiError(resp.status, body);
    }
    return body as T;
  }

  return {
    health: ({ signal }: RequestOptions = {}) =>
      request<HealthResponse>("/api/v1/health", { signal }),
    ready: ({ signal }: RequestOptions = {}) =>
      request<ReadyResponse>("/api/v1/ready", { signal }),
    /** Feed：游标分页，支持标签/地区/语言/类型/最低评分/关键词过滤。 */
    listDocuments: (params: DocumentQuery = {}, { signal }: RequestOptions = {}) =>
      request<DocumentListOut>(`/api/v1/documents${toQueryString(params)}`, { signal }),
    getDocument: (documentId: number, { signal }: RequestOptions = {}) =>
      request<DocumentDetailOut>(`/api/v1/documents/${documentId}`, { signal }),
    /** Signal：文档级 novelty（确定性工程指标，未经人工标注校准；响应里 calibrated=false）。 */
    getDocumentNovelty: (
      documentId: number,
      params: { window_days?: number; tau_hours?: number } = {},
      { signal }: RequestOptions = {},
    ) =>
      request<DocumentNoveltyOut>(
        `/api/v1/documents/${documentId}/novelty${toQueryString(params)}`,
        { signal },
      ),
    listClusters: (
      params: { limit?: number; min_docs?: number } = {},
      { signal }: RequestOptions = {},
    ) => request<ClusterOut[]>(`/api/v1/clusters${toQueryString(params)}`, { signal }),
    /** 采集底账日历：按天返回采集/富化量，前端按三态（正常/空转/断档/无底账）渲染。 */
    getCoverageCalendar: (days = 30, { signal }: RequestOptions = {}) =>
      request<CoverageCalendarOut>(`/api/v1/coverage/calendar?days=${days}`, { signal }),
    listSources: ({ signal }: RequestOptions = {}) =>
      request<SourceOut[]>("/api/v1/sources", { signal }),
    /** 列表：简报历史（默认日报）。 */
    listBriefs: (kind = "daily", limit = 20, { signal }: RequestOptions = {}) =>
      request<BriefListItem[]>(`/api/v1/briefs?kind=${kind}&limit=${limit}`, { signal }),

    // ---- 管理接口（需要 apiKey） ----
    updateSource: (sourceId: number, payload: SourceUpdate, { signal }: RequestOptions = {}) =>
      request<SourceOut>(`/api/v1/sources/${sourceId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
        headers: { "content-type": "application/json" },
        signal,
      }),
    runJob: (
      job: JobName,
      params: { force?: boolean; limit?: number; kind?: "daily" | "weekly" } = {},
      { signal }: RequestOptions = {},
    ) =>
      request<JobResultOut>(`/api/v1/admin/jobs/${job}/run${toQueryString(params)}`, {
        method: "POST",
        signal,
      }),
    /** 语义搜索：自然语言查询 → 向量近邻。 */
    search: (
      query: string,
      params: { limit?: number; min_similarity?: number } = {},
      { signal }: RequestOptions = {},
    ) =>
      request<SearchHitOut[]>(`/api/v1/search${toQueryString({ q: query, ...params })}`, {
        signal,
      }),

    /** 实体列表：默认按提及次数排序，可搜索。 */
    listEntities: (
      params: { q?: string; kind?: string; order?: "mentions" | "recent"; limit?: number } = {},
      { signal }: RequestOptions = {},
    ) => request<EntityOut[]>(`/api/v1/entities${toQueryString(params)}`, { signal }),
    /** 实体详情：时间线（按天）+ 最近提及的文档。 */
    getEntity: (
      entityId: number,
      params: { days?: number; recent_limit?: number } = {},
      { signal }: RequestOptions = {},
    ) =>
      request<EntityDetailOut>(`/api/v1/entities/${entityId}${toQueryString(params)}`, {
        signal,
      }),

    /** 疑似同一实体的候选对（管理台确认用）。 */
    listEntityCandidates: (
      params: {
        min_shared?: number;
        min_jaccard?: number;
        max_ratio?: number;
        limit?: number;
      } = {},
      { signal }: RequestOptions = {},
    ) =>
      request<EntityCandidateListOut>(
        `/api/v1/admin/entity-candidates${toQueryString(params)}`,
        { signal },
      ),
    /** 确认合并实体；remember 才会写回仓库里的别名表。 */
    applyEntityAliases: (
      payload: EntityAliasApplyIn,
      { signal }: RequestOptions = {},
    ) =>
      request<EntityAliasApplyOut>("/api/v1/admin/entity-aliases/apply", {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "content-type": "application/json" },
        signal,
      }),

    listRuns: (limit = 30, { signal }: RequestOptions = {}) =>
      request<FetchRunOut[]>(`/api/v1/admin/runs?limit=${limit}`, { signal }),
    listUsage: (days = 7, { signal }: RequestOptions = {}) =>
      request<LlmUsageOut[]>(`/api/v1/admin/usage?days=${days}`, { signal }),
    /** 最新一期简报；后端还没有生成过时返回 null（404）。 */
    getLatestBrief: async (kind = "daily", { signal }: RequestOptions = {}) => {
      try {
        return await request<BriefOut>(`/api/v1/briefs/latest?kind=${kind}`, { signal });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },

    // ---- 预测登记（推演可被证伪；概率一律「未经校准」） ----
    listPredictions: (
      params: { status?: string; limit?: number } = {},
      { signal }: RequestOptions = {},
    ) => request<PredictionListOut>(`/api/v1/predictions${toQueryString(params)}`, { signal }),
    getCalibration: (provider?: string, { signal }: RequestOptions = {}) =>
      request<CalibrationOut>(
        `/api/v1/predictions/calibration${provider ? `?provider=${encodeURIComponent(provider)}` : ""}`,
        { signal },
      ),
  };
}

export type HumanpulseClient = ReturnType<typeof createClient>;
