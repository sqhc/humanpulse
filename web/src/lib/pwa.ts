/** 只在生产构建里注册 Service Worker。
 *
 * 开发环境跳过有两个原因：Vite 的 dev server 每次都会重新编译模块，
 * SW 缓存会让改动"看不见"；而且本地调试时没人想要一个持久缓存。
 */
export function registerServiceWorker(options?: {
  isProd?: boolean;
  navigatorLike?: Pick<Navigator, "serviceWorker">;
  serviceWorkerUrl?: string;
}): Promise<ServiceWorkerRegistration | null> {
  const isProd = options?.isProd ?? import.meta.env.PROD;
  const nav = options?.navigatorLike ?? (typeof navigator === "undefined" ? undefined : navigator);
  const url = options?.serviceWorkerUrl ?? "/sw.js";

  if (!isProd || !nav || !("serviceWorker" in nav) || !nav.serviceWorker) {
    return Promise.resolve(null);
  }
  return nav.serviceWorker.register(url).catch((error: unknown) => {
    // 注册失败不应该影响应用可用性（例如 http 访问、隐私模式）
    console.warn("[humanpulse] service worker 注册失败，忽略", error);
    return null;
  });
}
