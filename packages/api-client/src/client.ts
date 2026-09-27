import type { paths } from "./generated/schema";

type JsonOf<T> = T extends { content: { "application/json": infer R } } ? R : never;

export type HealthResponse = JsonOf<paths["/api/v1/health"]["get"]["responses"][200]>;
export type ReadyResponse =
  | JsonOf<paths["/api/v1/ready"]["get"]["responses"][200]>
  | JsonOf<paths["/api/v1/ready"]["get"]["responses"][503]>;

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
  };
}

export type HumanpulseClient = ReturnType<typeof createClient>;
