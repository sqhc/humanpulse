import { createClient, type HumanpulseClient } from "@humanpulse/api-client";

/** 单例客户端；基地址来自 VITE_API_BASE_URL，留空则走同源反向代理。 */
export function createApiClient(apiKey?: string): HumanpulseClient {
  return createClient({
    baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
    apiKey,
  });
}
