# ADR-0005：主干可运行策略与上传门槛

- 状态：已接受
- 日期：2026-01
- 决策者：sqhc

## 背景

需求要求"确保修改不会导致项目无法运行后再上传"。单人开发没有评审搭档，因此需要把这条约束固化到工具链里，而不是靠自觉。

## 决策

1. **`main` 任意提交都必须可运行**：按 README 的步骤能起服务、能跑测试。
2. **本地门槛**：`make verify` 必须全绿才允许 commit/push。它包含
   - 后端 `ruff check` + `ruff format --check` + `mypy` + `pytest`
   - 前端 `eslint` + `tsc --noEmit` + `vitest` + `vite build`
   - `docker compose config -q`（两个 compose 文件语法校验）
3. **远端门槛**：`ci.yml` 在 push 与 PR 上跑后端、前端与契约检查；compose 冒烟另跑一个作业。
4. **契约不许悄悄漂移**：CI 重新导出 `backend/openapi.json` 并重新生成 `packages/api-client/src/generated/schema.d.ts`，用 `git diff --exit-code` 校验两者与仓库一致。
5. **分批交付**：每个阶段作为一个可运行的里程碑提交；跨阶段的大改走 `feat/<slug>` 分支 + PR，CI 全绿后 squash 合并。禁止"先把跑不起来的中间态推上去再说"。
6. **失败即停**：任何一步红了，先修好再继续，不做"先传后修"。
7. **回滚**：每个阶段打 tag（`v0.0.0-phase0` …）；回滚用 `git revert` 并部署上一 tag 的镜像。

## 后果

- 单人项目也要维护 CI 与契约测试，前期有成本；换来的是任何时候都能安全接手、安全部署。
- 因为 `main` 始终可运行，VPS 上的 `pull` 不会再遇到"镜像起不来"的意外（构建失败时 CI 不会产出镜像）。
