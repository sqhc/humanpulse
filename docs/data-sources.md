# 数据源清单与配额

维护规则：新增任何源必须在 `infra/seed/sources.yaml` 登记 `license` 字段，并在此文档补充配额/限制说明。政策边界见 [ADR-0002](adr/0002-data-source-policy.md)。

## 实测状态（2026-09，逐个 curl + 真实采集验证）

`enabled: true` 的源全部至少成功采集过一轮；下表是当时的结果与坑。

| 源 | 类型 | 实测 | 注意事项 |
| --- | --- | --- | --- |
| Al Jazeera / BBC World / France 24 / UN News / NPR / Guardian / DW | `rss` | ✅ 200 | 单轮 10–30 条；用 ETag/Last-Modified 条件请求 |
| BBC 中文 / 纽约时报中文网 / RFI 中文 / RFA 中文 | `rss` | ✅ 200 | 中文语料主力；`pubDate` 可解析 |
| 新增中文源（中央社/公视/端传媒/DW中文/VOA中文/中国数字时代/中国新闻网/界面新闻） | `rss` | ✅ 200 | 2026-09 扩充，中文源合计 **12** 个；逐源证据见"中文源扩充实测"小节 |
| Crisis Group / Ars Technica / Nature / Science / MIT Tech Review / Rest of World | `rss` | ✅ 200 | 议题专用，频率放低（2–6 小时） |
| Hacker News front page | `rss` | ✅ 200 | tier 3，低权重 |
| GDELT DOC 2.0 | `gdelt` | ⚠️ 不稳定 | 见下方"GDELT"小节 |
| 手动上传 | `manual` | ✅ | 需管理员 Key + 勾选权利声明；单文件 ≤ 25 MB，仅文本类 |

### 中文源扩充实测（2026-09）

在 2026-09-29 用**真实采集客户端**（`httpx` + `feedparser`，与 `RssCollector` 同一路径）逐个复验；判定标准：状态码 200、可解析出条目、最新一条发布时间在 7 天内。条目数为采集器实际产出（受 `rss_max_items_per_feed` 截断）。

| 新增源 | URL | HTTP | 条目数 | 最新一条（UTC） | 距今 |
| --- | --- | --- | --- | --- | --- |
| 中央社 国际焦点 | `https://feeds.feedburner.com/rsscna/intworld` | ✅ 200 | 20 | 2026-09-29 12:32 | 0.0 天 |
| 公视新闻 | `https://news.pts.org.tw/xml/newsfeed.xml` | ✅ 200 | 25 | 2026-09-29 13:01 | 0.0 天 |
| 端传媒 | `https://theinitium.com/rss/` | ✅ 200 | 15 | 2026-09-29 10:30 | 0.1 天 |
| 德国之声中文 | `https://rss.dw.com/rdf/rss-chi-all` | ✅ 200 | 30 | 2026-09-29 12:21 | 0.0 天 |
| 美国之音中文 | `https://www.voachinese.com/api/zm_yql-vomx-tpeybti` | ✅ 200 | 20 | 2026-09-28 22:28 | 0.6 天 |
| 中国数字时代 | `https://chinadigitaltimes.net/chinese/feed` | ✅ 200 | 7 | 2026-09-29 06:45 | 0.3 天 |
| 中国新闻网 | `https://www.chinanews.com.cn/rss/scroll-news.xml` | ✅ 200 | 30 | 2026-09-29 13:09 | 0.0 天 |
| 界面新闻 | `https://a.jiemian.com/index.php?m=article&a=rss` | ✅ 200 | 30 | 2026-09-29 13:02 | 0.0 天 |

- 端传媒、中国数字时代走 Cloudflare，但**对当前 UA 返回 200**（与 Amnesty 的稳定 403 不同），本轮可用；仍依赖单源熔断兜底。
- 已实测可用但本轮未启用的备用源（避免中文源超过 12 个）：中央社 两岸透视、中国新闻网 要闻导读、美国之音 台湾、RTI 中央广播电台、爱范儿、少数派。

### 已移除 / 已停用

| 源 | 现象 | 处理 |
| --- | --- | --- |
| Reuters | 我原先用的 feed URL 返回 **404** | 移除，由 France 24 / NPR 补位 |
| AP News | **403**（拒绝非浏览器客户端） | 移除 |
| 澎湃新闻 | RSS **404**（2026-09 复核仍为 404） | 移除 |
| 新华网国际 | `http://www.xinhuanet.com/world/news_world.xml` 返回 **200**，但内容是 **2022 年的静态 XML**，且没有 `pubDate` | 移除；同时新增 `max_item_age_days`（默认 45 天）兜底，有发布时间的过期内容一律记 `rejected/too_old` |
| Amnesty International | curl 200，**Python httpx 稳定 403**（`server: cloudflare`，TLS 指纹被判非浏览器） | **停用**，按 ADR-0002 不做反爬绕过 |
| 关键评论网 | 首页 403（`server: cloudflare`）；`/feed` **404**、`/rss` **403** | 移除 |
| 明报 | RSS 路径 403（Cloudflare） | 移除 |
| 自由时报 | 首页与 `/rss/*.xml` 全部 403（nginx，拒绝非浏览器） | 移除 |
| 世界新闻网 | `/feed` 404、`/rss` 403（Cloudflare） | 移除 |
| 联合早报 | 官方 `/rss/*` 与 `/rss.xml` 全部 **404**；仅第三方聚合代理（`plink.anyfeeder.com`）可用 | 移除（不接第三方聚合） |
| 三立 / 财新 / 观察者网 / 36氪 | 返回 **200 但 `content-type` 是 HTML**、解析出 0 条目（不是 feed） | 移除 |
| 央视新闻 | `/rss/china.xml` 404 | 移除 |
| 人民网 | 200 且 100 条，但最新一条为 **2025-06-05**（约 482 天前），已停更 | 移除（静态/停更，同新华网） |
| ETtoday | 200 且 50 条，但 `pubDate` 写作 `Tue,29 Sep 2026 20:59:00  +0800`（逗号后缺空格，非 RFC822），feedparser 解析不出时间，**无法验证时效** | 移除 |
| 联合新闻网（UDN） | feed 可解析，但 `pubDate` 被解析成 **1970-01-01**（坏日期） | 移除 |
| 香港01 / 独立媒体 | `/feed` 404 / 403（Cloudflare） | 移除 |
| 中央社（旧 FeedBurner 别名） | `rsscna/mainnews`、`intnews`、`focus` 均 404 | 改用分类 feed `rsscna/intworld` |

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
