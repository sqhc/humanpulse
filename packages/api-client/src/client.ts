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

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const resp = await doFetch(`${baseUrl}${path}`, {
      ...init,
      headers: { accept: "application/json", ...(init.headers ?? {}) },
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
  };
}

export type HumanpulseClient = ReturnType<typeof createClient>;
