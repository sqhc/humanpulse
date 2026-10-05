/* humanpulse service worker：只缓存应用外壳，不缓存接口数据。
 *
 * 为什么不用 vite-plugin-pwa：那会引入一套构建期配置与依赖；这里只有一条规则，
 * 手写更容易审计，也方便在离线策略上保持保守——
 * **API 响应一律不缓存**：这是一份新闻类数据，过期数据比没有数据更糟。
 */
const SHELL_CACHE = "humanpulse-shell-v1";
const SHELL_ASSETS = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // 接口与流：始终走网络，绝不缓存（实时数据 + 避免把 404 固化）
  if (url.pathname.startsWith("/api/")) return;

  // 导航请求：网络优先，断网时回退到缓存的外壳
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/index.html").then((hit) => hit ?? Response.error())),
    );
    return;
  }

  // 静态资源：缓存优先（Vite 产物带 hash，不会串版本）
  event.respondWith(
    caches.match(request).then((hit) => {
      if (hit) return hit;
      return fetch(request).then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});
