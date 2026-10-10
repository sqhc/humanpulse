# ADR-0012：让语义向量真正生效（模型一致性 + 离线重建的时间窗）

- 状态：已接受
- 日期：2026-10
- 决策者：sqhc

## 背景

ADR-0003 就定了「生产用 local 语义向量」。这次真的装上 sentence-transformers 重跑 make reembed，
结果暴露出**两个此前没发现的缺陷**——而且第一个会让人得出完全错误的结论。

## 缺陷一：离线重建的时间窗锚在墙钟上（真 bug）

find_nearest 原本把窗口起点写死为 datetime.now() - 24h。这在实时采集时没问题，
但 make reembed 是**离线重放历史数据**：当时库里最新一篇是 2026-10-05，墙钟是 2026-10-10，
于是窗口内 0 篇文档，每篇都各自成簇。

症状是 reembed 报 multi_doc_clusters: 0（对照：此前的 hash 存量有 13 个多文档簇），
**看起来像语义向量完全没用，实际是时间窗失效，与向量质量无关。**

修复：
- 新增 window_anchor(published_at, fetched_at, reference)：锚点取文档自身时间，两者都缺才退回 reference；
  顺带防脏数据（fetched_at 明显早于 published_at 时信任 published_at）；
- find_nearest 接受 anchor 参数，窗口改为**双向**（since <= t <= until），
  这样同批次一起入库的文档也能互相看见；
- is_recent() 让 is_hot（热点阈值）同样相对 anchor 判断，否则离线重建会把所有文档当冷数据；
- attach_cluster 用文档时间做 anchor。实时采集语义不变（文档时间约等于 now）。

修复后同一批数据的真实结果：**0 → 50 个多文档簇**（最大 11 篇）。

## 缺陷二：向量模型不一致时静默返回垃圾结果

重建向量后，API 容器里 EMBEDDING_PROVIDER 仍是 hash，于是搜索会**拿 hash 查询向量去比对 local 文档向量**——
两个不同向量空间做余弦相似度，返回的是一串看似合理、实则无意义的数字。

修复：/search 先查 embeddings.model 去重集合，与当前 embedder.name 不符时返回 **409** 并说明补救方式
（make reembed 或改回配置）。宁可报错，也不要给出误导性的排序。

## 顺带：镜像与部署

- API 需要在请求时编码查询向量，所以 **local 向量要求 API 镜像装 ml extra**（约 1GB 依赖）；
- Dockerfile 加 ARG WITH_ML=0：默认不装（CI/开发用 hash，镜像小），生产用 --build-arg WITH_ML=1；
- 构建期用 docker/prefetch_model.py 预下载模型权重并设 HF_HOME——
  **运行时不该依赖 HuggingFace 可达**（网络/限流会让首个搜索请求失败，版本也无法审计）；
- 已实测镜像内 HF_HUB_OFFLINE=1 可离线加载模型（dim=384）。

镜像体积：**19.7GB -> 4.28GB**（-78%）。原因是 PyPI 上的 linux torch wheel 会连带拉 cuda-toolkit / nvidia-* 全套；改用 PyTorch 的 CPU 专用索引后（[[tool.uv.index]] + tool.uv.sources），lock 里已无 cuda-toolkit/nvidia/triton，torch 变为 2.14.1+cpu。

**踩到的坑**：torch 是 sentence-transformers 的**传递依赖**，而 tool.uv.sources 只覆盖**直接依赖**——必须把 torch>=2.14 显式写进 ml extra，索引才会生效（否则静默继续用 PyPI）。
生产应改用 CPU 专用 torch（--index-url https://download.pytorch.org/whl/cpu）把体积压到约 1-2GB，
这是下一步的部署任务，本次先把功能链路跑通。

## 实测效果（803 篇真实文档，local 向量，阈值 0.85）

**聚类**（跨语言合并是 hash 做不到的）：

| 簇 | 篇数 | 来源数 | 内容 |
| --- | --- | --- | --- |
| 2468 | 9 | 8 | FBI 涉台谍案——中文（美国之音/公视/DW中文）与英文（NPR/DW）合并 |
| 2144 | 8 | 6 | 南非枪击 27 人（Al Jazeera/BBC/France 24/Guardian） |
| 2168 | 6 | 6 | 瑞士中立公投（France 24/BBC/DW/Guardian/Al Jazeera） |
| 2103 | 6 | 4 | 霍尔木兹——中文（RFI 中文）与英文（Guardian/DW/NPR）合并 |

**搜索**（同批查询下 hash 与 local 的对比）：

| 查询 | hash 的第 2 条 | local 的第 2 条 |
| --- | --- | --- |
| 霍尔木兹航运风险 | Church confronts shock of abuse crisis（0.265） | Is Iran charging a toll through Hormuz（0.486） |
| 美中贸易谈判 | US ban on Canadian alcohol（0.262） | 特朗普与习近平会晤相关（0.611） |
| AI 模型发布 | 挪威拟禁 AI 眼镜（0.284） | OpenAI 因安全隐患暂缓发布新模型（0.606） |

中文查询也成立：「中东战争对油价的影响」首条是「美伊战争重塑海湾地缘政治…恐危及石油美元体系」（0.729）。

## 后果

- 阈值 VECTOR_DUP_THRESHOLD=0.85 对 local 向量是**合适**的（与「完全相同标题」参考标准的 Rand 指数 0.9997），
  暂不调整；0.80 会多合并 17 个簇，抽查未发现误合并，可作为备选。
- make reembed 现在是可信的离线工具：可以在任意时间点重放历史数据。
- 切换到 local 后，**API 与 worker 都必须用带 ml 的镜像**，否则搜索 409、处理流程报错。
- 部署前必须解决 19.7GB 镜像问题（CPU-only torch）。
