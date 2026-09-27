# 数据源清单与配额

维护规则：新增任何源必须在 `infra/seed/sources.yaml` 登记 `license` 字段，并在此文档补充配额/限制说明。政策边界见 [ADR-0002](adr/0002-data-source-policy.md)。

## MVP（Phase 1 启用）

| 源 | 类型 | 鉴权 | 限额 / 注意事项 |
| --- | --- | --- | --- |
| 各家国际新闻 RSS | `rss` | 无 | 使用 ETag/Last-Modified 条件请求；单源最短间隔 30 分钟 |
| GDELT DOC 2.0 | `gdelt` | 无 | 文档建议请求间隔 ≥5 秒；一次最多 250 条，默认取 75 条 |
| ReliefWeb API (OCHA) | `reliefweb` | 无（建议带 appname） | 每请求 `limit` ≤ 1000，默认 50；建议 2 分钟一次 |
| 手动上传 | `manual` | 管理员 API Key | 用户须勾选权利声明；单文件 ≤ 25 MB |

## Phase 2

| 源 | 类型 | 鉴权 | 限额 / 注意事项 |
| --- | --- | --- | --- |
| UCDP GED API | `ucdp` | 无 | 数据集按版本发布，日更足够；需署名 |
| Reddit | `reddit` | OAuth（script app） | 100 QPM（免费档）；只读 `/new` 与搜索 |
| Bluesky | `bluesky` | App Password（专用账号） | 公开 XRPC；注意分页游标与速率 |
| Mastodon | `mastodon` | 无 | 实例公开时间线；不同实例限额不同，单实例节流 1 req/s |

## 需要注册、默认关闭

| 源 | 原因 |
| --- | --- |
| ACLED | 需申请 API key；**许可仅限非商业/研究用途**。启用前必须评估用途并在 ADR-0002 记录 |
| YouTube Data API | 10,000 units/天；官方接口**无法**下载第三方视频字幕（`captions.download` 仅限自有视频），字幕仅支持上传者提供的文件 |

## 明确不接入

| 源 | 原因 |
| --- | --- |
| X / Twitter | 2025 起按量付费；未授权抓取有条款与法律风险。个人项目不接受该成本，**不在路线图内** |
| 需绕过 Cloudflare / 登录墙的站点 | 违反站点条款，且技术上不可靠 |
| Apify 等第三方聚合抓取服务 | 成本不可控、合规责任不清晰 |

## 新增源的检查清单

1. 该源是否有官方 API 或 RSS？优先使用。
2. `robots.txt` 是否允许？条款是否允许程序化访问？
3. 是否需要署名？署名信息写进 `license` 字段与 `/about` 页面。
4. 限额是多少？据此设置 `cadence_minutes` 与节流。
5. 是否含个人数据？如是，确认只涉及公开报道中的公众人物。
6. 在 `infra/seed/sources.yaml` 登记，并更新本文档。
