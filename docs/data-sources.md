# 数据源清单与配额

维护规则：新增任何源必须在 `infra/seed/sources.yaml` 登记 `license` 字段，并在此文档补充配额/限制说明。政策边界见 [ADR-0002](adr/0002-data-source-policy.md)。

## 实测状态（2026-09，逐个 curl + 真实采集验证）

`enabled: true` 的源全部至少成功采集过一轮；下表是当时的结果与坑。

| 源 | 类型 | 实测 | 注意事项 |
| --- | --- | --- | --- |
| Al Jazeera / BBC World / France 24 / UN News / NPR / Guardian / DW | `rss` | ✅ 200 | 单轮 10–30 条；用 ETag/Last-Modified 条件请求 |
| BBC 中文 / 纽约时报中文网 / RFI 中文 / RFA 中文 | `rss` | ✅ 200 | 中文语料主力；`pubDate` 可解析 |
| Crisis Group / Ars Technica / Nature / Science / MIT Tech Review / Rest of World | `rss` | ✅ 200 | 议题专用，频率放低（2–6 小时） |
| Hacker News front page | `rss` | ✅ 200 | tier 3，低权重 |
| GDELT DOC 2.0 | `gdelt` | ⚠️ 不稳定 | 见下方"GDELT"小节 |
| 手动上传 | `manual` | ✅ | 需管理员 Key + 勾选权利声明；单文件 ≤ 25 MB，仅文本类 |

### 已移除 / 已停用

| 源 | 现象 | 处理 |
| --- | --- | --- |
| Reuters | 我原先用的 feed URL 返回 **404** | 移除，由 France 24 / NPR 补位 |
| AP News | **403**（拒绝非浏览器客户端） | 移除 |
| 澎湃新闻 | RSS **404** | 移除 |
| 新华网国际 | `http://www.xinhuanet.com/world/news_world.xml` 返回 **200**，但内容是 **2022 年的静态 XML**，且没有 `pubDate` | 移除；同时新增 `max_item_age_days`（默认 45 天）兜底，有发布时间的过期内容一律记 `rejected/too_old` |
| Amnesty International | curl 200，**Python httpx 稳定 403**（`server: cloudflare`，TLS 指纹被判非浏览器） | **停用**，按 ADR-0002 不做反爬绕过 |

> 教训：**HTTP 200 不等于源可用**。巡检必须看"最新一条的发布时间"，而不是状态码——新华网那条就是靠内容标题（"二十大后…"）才发现的。

### GDELT

- 官方文档说"请求间隔 ≥5 秒"，实测 **6 秒仍会 429**，因此节流放宽到 `GDELT_THROTTLE_SECONDS=12`，并在采集器里对 429/5xx 做退避重试（最多 3 次，尊重 `Retry-After`）。
- GDELT `artlist` 模式**只给标题 + 域名，没有正文**。这类条目走 `headline` 提示词（摘要必须以"（仅据标题）"开头、不许补细节），并打上 `headline-only` 标签。
- 同一轮里两个 GDELT 源仍可能互相踩限流；失败会由单源熔断（连续 3 次自动停用）接管。

### 需要注册或尚无采集器（默认 `enabled: false`）

| 源 | 原因 |
| --- | --- |
| ReliefWeb (OCHA) | **v1 已下线**（410），v2 要求 **approved appname**（403）。申请地址：<https://apidoc.reliefweb.int/parameters#appname>；获批后改 `enabled: true` 并实现 `kind=reliefweb` 的采集器 |
| UCDP GED | 免费，但尚未实现 collector |
| ACLED | 需申请 API key；**许可仅限非商业/研究用途**。启用前必须评估用途并在 ADR-0002 记录 |

## Phase 2 计划接入

| 源 | 类型 | 鉴权 | 限额 / 注意事项 |
| --- | --- | --- | --- |
| Reddit | `reddit` | OAuth（script app） | 100 QPM（免费档）；只读 `/new` 与搜索 |
| Bluesky | `bluesky` | App Password（专用账号） | 公开 XRPC；注意分页游标与速率 |
| Mastodon | `mastodon` | 无 | 实例公开时间线；不同实例限额不同，单实例节流 1 req/s |
| YouTube Data API | — | API key | 10,000 units/天；官方接口**无法**下载第三方视频字幕（`captions.download` 仅限自有视频） |

## 明确不接入

| 源 | 原因 |
| --- | --- |
| X / Twitter | 2025 起按量付费；未授权抓取有条款与法律风险。个人项目不接受该成本，**不在路线图内** |
| 需绕过 Cloudflare / 登录墙的站点 | 违反站点条款；实测 Python 客户端会被 Cloudflare 403，我们选择停用而不是绕过 |
| Apify 等第三方聚合抓取服务 | 成本不可控、合规责任不清晰 |

## 新增源的检查清单

1. 该源是否有官方 API 或 RSS？优先使用。
2. `robots.txt` 是否允许？条款是否允许程序化访问？
3. 是否需要署名？署名信息写进 `license` 字段与 `/about` 页面。
4. 限额是多少？据此设置 `cadence_minutes` 与节流。
5. **最新一条的发布时间是什么时候？**（防止静态/归档 XML 混入）
6. 是否含个人数据？如是，确认只涉及公开报道中的公众人物。
7. 在 `infra/seed/sources.yaml` 登记并跑一轮真实采集，再更新本文档。
