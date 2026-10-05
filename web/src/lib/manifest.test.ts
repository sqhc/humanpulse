/** 清单文件是 PWA 安装的前提，字段缺失浏览器会静默忽略安装提示。 */

import { describe, expect, it } from "vitest";

import icon192 from "../../public/icon-192.png?url";
import icon512 from "../../public/icon-512.png?url";
import manifestRaw from "../../public/manifest.webmanifest?raw";

const manifest = JSON.parse(manifestRaw) as {
  name?: string;
  short_name?: string;
  start_url?: string;
  display?: string;
  theme_color?: string;
  icons?: { src: string; sizes: string; purpose?: string }[];
};

describe("manifest.webmanifest", () => {
  it("包含安装所需字段", () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.theme_color).toMatch(/^#/);
  });

  it("图标覆盖 192 与 512，且有一张声明 maskable", () => {
    const sizes = (manifest.icons ?? []).map((icon) => icon.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
    expect((manifest.icons ?? []).some((icon) => icon.purpose?.includes("maskable"))).toBe(true);
  });

  it("声明的图标文件真实存在（由打包器解析到 URL）", () => {
    const sources = (manifest.icons ?? []).map((icon) => icon.src);
    expect(sources).toContain("/icon-192.png");
    expect(sources).toContain("/icon-512.png");
    expect(icon192).toBeTruthy();
    expect(icon512).toBeTruthy();
  });
});
