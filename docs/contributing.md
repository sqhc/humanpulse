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

## 仓库自动化与凭据

### 本机 push

本机以 HTTPS 推送，凭据来自 macOS keychain（classic PAT，作用域 `repo`、`workflow`）。
注意：`.github/workflows/**` 的改动需要 `workflow` 作用域，换 token 时不要漏。

### 关于 DSH 的 GitHub MCP 连接

权限已升级：现在可读取本私有仓库（commits / branches / 文件内容）。
建仓仍走本机 REST（keychain 里的 classic PAT，作用域 `repo`、`workflow`），MCP 用于日常查看与管理。

### 受限沙箱下的缓存重定向

在 workspace-write 沙箱里，`uv` 与 `docker buildx` 会尝试写 `~/.cache/uv`、`~/.docker/buildx`，
这两个路径在写入白名单外会被拒绝。`Makefile` 因此把两者重定向到仓库内的 `.cache/`：

```make
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
BUILDX_CONFIG ?= $(CURDIR)/.cache/buildx
export UV_CACHE_DIR
export BUILDX_CONFIG
```

- 两处都已在 `.gitignore` 中；可用 `UV_CACHE_DIR=/path make verify` 覆盖。
- GitHub Actions 运行器没有该限制，因此 CI 配置里不需要任何相关设置。

### Node 版本必须优先命中 24（本机）

PATH 里别的 `node`（例如 conda 自带的 v20）会被优先解析，而 vitest 5 + jsdom 30 要求 Node ≥ 22.12，
症状是 `Failed to start forks worker ... undici ... markAsUncloneable is not a function`。
跑前端命令前**前置**（不是追加）nvm 的 bin：

```bash
export PATH="/Users/shenqing/.nvm/versions/node/v24.21.0/bin:$PATH"
node -v   # 期望 v24.x
```

CI 用 `actions/setup-node` 固定 22.x，不受影响。

### CI/CD 需要的 Secrets 与 Variables

在仓库 Settings → Secrets and variables → Actions 中配置：

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `DEPLOY_HOST` | Secret | VPS 地址 |
| `DEPLOY_USER` | Secret | SSH 用户 |
| `DEPLOY_PATH` | Secret | VPS 上的仓库路径（如 `/opt/humanpulse`） |
| `DEPLOY_SSH_KEY` | Secret | 部署用私钥（只授权该主机） |
| `GHCR_TOKEN` | Secret | VPS 拉取私有镜像用的 PAT（`read:packages`） |
| `DEPLOY_ENABLED` | **Variable** | 设为 `true` 才会在打 tag 后自动部署；默认不部署 |

`GITHUB_TOKEN` 由 Actions 自动提供，用于推送镜像到 GHCR（workflow 已声明 `packages: write`）。

## 提交前自查清单

- [ ] `make verify` 全绿
- [ ] 新功能有对应测试（后端 pytest / 前端 vitest）
- [ ] 接口变更已重新生成 api-client 与 openapi.json
- [ ] 涉及数据源/合规的改动已更新 ADR 或 data-sources.md
- [ ] 没有把密钥、`.env`、`uploads/` 提交进去
