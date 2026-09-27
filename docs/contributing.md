# 贡献与上传规则

## 黄金规则

**`main` 上的每一次提交都能跑起来**（[ADR-0005](adr/0005-green-main.md)）。上传前必须：

```bash
make verify      # lint + typecheck + test + build + compose 校验，必须全绿
```

任何一步红了就先修，不要"先传后修"。

## 分支与 PR

单人项目也走分支，理由是保留可回滚的历史与 CI 记录：

1. `git switch -c feat/<slug>`（或 `fix/<slug>`、`docs/<slug>`）
2. 小步提交，提交信息用 `<type>(<scope>): <subject>`
   - type：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`
   - scope 示例：`api`、`web`、`pipeline`、`collector`、`infra`、`docs`
3. 推送并开 PR；CI 全绿且自查通过后 squash 合并
4. 阶段完成时打 tag：`v0.0.0-phase0`、`v0.1.0` …

## 改动契约时

接口变更必须同步生成物，否则 CI 的契约检查会失败：

```bash
make openapi                        # 重新导出 backend/openapi.json
pnpm run api-client:generate        # 重新生成 packages/api-client/src/generated/schema.d.ts
```

**生成文件禁止手改**（`packages/api-client/src/generated/`）。

## 新增数据源

必须读 [ADR-0002](adr/0002-data-source-policy.md) 与 [data-sources.md](data-sources.md) 的检查清单；在 `infra/seed/sources.yaml` 登记 `license` 字段。涉及 X 抓取、反爬绕过、需要注册的源（如 ACLED）默认拒绝，除非先更新 ADR。

## 代码约定

- 后端：Python 3.12，`ruff`（line-length 100）+ `mypy` 严格度见 `backend/pyproject.toml`；新增模块配单测。
- 前端：TypeScript `strict`；组件保持无副作用；数据访问统一走 `@humanpulse/api-client`，不要在组件里手写 `fetch`。
- 提示词：`app/llm/prompts/*.md`，改动必须升版本号并说明动机。
- 注释与文档：写"为什么"，不写"做了什么"。

## 提交前自查清单

- [ ] `make verify` 全绿
- [ ] 新功能有对应测试（后端 pytest / 前端 vitest）
- [ ] 接口变更已重新生成 api-client 与 openapi.json
- [ ] 涉及数据源/合规的改动已更新 ADR 或 data-sources.md
- [ ] 没有把密钥、`.env`、`uploads/` 提交进去
