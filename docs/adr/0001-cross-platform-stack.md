# ADR-0001：跨端技术栈选择

- 状态：已接受
- 日期：2026-01
- 决策者：sqhc

## 背景

平台需要同时服务 Web、桌面与移动端，且要在个人项目的人力预算内长期维护。

## 决策

1. **后端是唯一数据源**：FastAPI 提供 `/api/v1` REST 契约，所有客户端只通过它取数。
2. **跨端复用的是契约，不是 UI**：
   - REST 契约（OpenAPI 3.1，由 FastAPI 自动生成）
   - `packages/api-client`（类型由 OpenAPI 生成，禁止手改生成文件）
   - `packages/design-tokens`（语义色板/间距/圆角）
3. **MVP 只做 Web**：React 19 + Vite + TypeScript + Tailwind v4 + TanStack Query。
4. **桌面端（Phase 3）用 Tauri 2 封装同一份 Web 构建产物**，不重写 UI。
5. **移动端（Phase 3）优先 PWA，其次 Expo/React Native**，复用 `api-client` 与 design tokens。
6. **不采用 Dioxus 单代码库路线（路线 B）**：Dioxus 0.7 已具备 Tailwind、Subsecond 热补丁与移动端支持，但 Rust + WASM 的移动端调试与生态成本对个人项目不划算。若未来性能或包体积成为瓶颈，可重新评估。

## 后果

- 优点：Web 最快可用；桌面端几乎零成本；契约测试（OpenAPI 快照 + 生成物 diff）能在 CI 中防止接口悄悄破坏客户端。
- 代价：Tauri / Expo 只是外壳与原生能力补充，移动端体验弱于纯原生；接受此折中直到 Phase 3 再评估。
