/** 跨端共享的设计变量；Web / 桌面 / 移动共用同一套语义色板。 */
export const colors = {
  surface: "#0b0f14",
  surfaceMuted: "#131a22",
  border: "#233043",
  text: "#e6edf5",
  textMuted: "#93a3b8",
  accent: "#3fb6a8",
  danger: "#ef6b6b",
  warning: "#e5b567",
} as const;

export const lightColors = {
  surface: "#f8fafc",
  surfaceMuted: "#eef2f7",
  border: "#d8e0ea",
  text: "#10161d",
  textMuted: "#4d5b6d",
  accent: "#0f766e",
  danger: "#b42318",
  warning: "#8a5a00",
} as const;

export const spacing = {
  xs: "0.25rem",
  sm: "0.5rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2.5rem",
} as const;

export const radius = { sm: "0.375rem", md: "0.75rem", lg: "1.25rem" } as const;

export const fontStack =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", "PingFang SC", "Noto Sans CJK SC", sans-serif';

export type ColorToken = keyof typeof colors;
export type SpacingToken = keyof typeof spacing;
