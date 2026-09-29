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

/** 结构化简报内容（由服务端渲染 Markdown，前端按语言取字段）。 */
export interface BriefSection {
  key: string;
  heading_zh: string;
  heading_en: string;
  bullets_zh: string[];
  bullets_en: string[];
}

export interface BriefContentShape {
  title_zh?: string;
  title_en?: string;
  overview_zh?: string;
  overview_en?: string;
  sections?: BriefSection[];
  closing_zh?: string;
  closing_en?: string;
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
    listClusters: (
      params: { limit?: number; min_docs?: number } = {},
      { signal }: RequestOptions = {},
    ) => request<ClusterOut[]>(`/api/v1/clusters${toQueryString(params)}`, { signal }),
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
  };
}

export type HumanpulseClient = ReturnType<typeof createClient>;
