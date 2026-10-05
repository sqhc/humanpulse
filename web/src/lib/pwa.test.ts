import { describe, expect, it, vi } from "vitest";

import { registerServiceWorker } from "./pwa";

describe("registerServiceWorker", () => {
  it("开发环境不注册（Vite dev server 会被缓存干扰）", async () => {
    const register = vi.fn();
    const result = await registerServiceWorker({
      isProd: false,
      navigatorLike: { serviceWorker: { register } } as unknown as Navigator,
    });
    expect(result).toBeNull();
    expect(register).not.toHaveBeenCalled();
  });

  it("生产环境注册 /sw.js", async () => {
    const registration = { scope: "/" } as ServiceWorkerRegistration;
    const register = vi.fn().mockResolvedValue(registration);
    const result = await registerServiceWorker({
      isProd: true,
      navigatorLike: { serviceWorker: { register } } as unknown as Navigator,
    });
    expect(register).toHaveBeenCalledWith("/sw.js");
    expect(result).toBe(registration);
  });

  it("浏览器不支持 serviceWorker 时不报错", async () => {
    const result = await registerServiceWorker({
      isProd: true,
      navigatorLike: {} as unknown as Navigator,
    });
    expect(result).toBeNull();
  });

  it("注册失败只告警，不影响应用", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const register = vi.fn().mockRejectedValue(new Error("insecure context"));
    const result = await registerServiceWorker({
      isProd: true,
      navigatorLike: { serviceWorker: { register } } as unknown as Navigator,
    });
    expect(result).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
