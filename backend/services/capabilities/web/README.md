# Web Capability Plane



Unified orchestration for web fetch, heavy dynamic crawl, and fast-lane read.



Application and MiddleAgent must import from this package — not `services.agno_web_service` shims.



| Module | Role |

|---|---|

| `web_orchestration_service.py` | sync fetch、search 信号、fast path 网页块编排 |

| `static_body_extract.py` | 静态 HTML 正文优先抽取（容器定位 → 噪音删除 → 保守尾部裁剪） |

| `async_web_pipeline.py` | `web_heavy_fetch` 后台任务执行 |



## Static body extraction



`static_body_extract.minimal_html_to_plain_text` 供 fast path 直抓与静态入库共用，策略三层：



1. **正文容器评分** — 收集 `article` / `main` / 常见正文 class 及块级节点，按段落密度、链接密度打分；剔除被更高分子节点包裹的父容器，避免「大 main + 侧栏」整页入选。

2. **通用噪音删除** — 页级移除 nav/header/footer/aside/TOC 侧栏；容器内再删 figure/figcaption、分享/评论/推荐/广告块；行级移除广告标记、摄影署名与跨站 UI chrome。

3. **文首 TOC 裁剪** — 连续短行/无句读目录项（≥4 行）裁至首段正文；保留紧随其后的章节标题（如「产品介绍」）。

4. **保守尾部裁剪** — 高置信尾部 marker（如「相关文章」「推荐阅读」「下载 PDF」「向他人分享」）仅在正文足够长且出现在后段时截断。

5. **断行合并** — 短 span 断句与孤立编号行（`1.` / `：1.`）保守合并。

6. **单次 trafilatura 回退** — 规则抽取质量仍差（过短、目录占比过高）时，在 `minimal_html_to_plain_text` 内调用 `tools.web.common.extract_with_trafilatura` 一次，仍从同一入口输出；不新开 lane。



Helper 函数（`line_is_generic_chrome`、`apply_conservative_tail_trim`、`normalize_extracted_lines` 等）均定义在 `static_body_extract.py`，编排层只 import 入口函数，不下沉到 `tools/`。

行后处理（`normalize_extracted_lines`）：断行合并（含编号行）→ 相邻重复折叠 → 文首 TOC 裁剪 → … → 保守尾部 marker 裁剪 → …。纯 `#` Markdown 空标题行在 `line_is_generic_chrome` 阶段丢弃。



## Async control plane



- Task type: `web_heavy_fetch`

- Enqueue via `services.execution.task_plane_service.enqueue_web_heavy_fetch_task`

- Worker: `workers.entry.task_plane_worker` → `async_dispatcher.process_async_task`



## Feature flags



- `ENABLE_FAST_LANE_WEB` — web fast path

- `ENABLE_ASYNC_CONTROL_PLANE_V2` — 后台重抓取

