# MVP、原型与下一阶段优先级

用途：
- 区分 **MVP（已验证命题）**、**当前原型（已超过 MVP）**、**下一步 P0/P1/P2**
- 避免把「当时最小验证范围」误读成「现在还没有的能力」
- 与 [01_项目卡](01_项目卡.md)、[02_简版PRD](02_简版PRD.md)、[12_求职展示版项目说明](12_求职展示版项目说明.md) 对齐

关联：
- 能力/路由验收：[06_路由与能力测试矩阵](06_路由与能力测试矩阵.md)、[05_评测与验收体系](05_评测与验收体系.md)
- 工程事实源：`docs/current/03_目标运行路径与架构验收表.md`

---

## 1. MVP（已验证的最小命题）— 过去时

MVP 不是「功能越少越好」，而是 **用最少但稳定的闭环，验证产品命题是否成立**。

### 1.1 要验证什么

- **统一入口**：`POST /chat/agno` 承载默认主链
- **默认路径 + 升级路径**：Fast 优先；复杂 / 材料不足时可升级到 Complex（及必要时 Async）
- **统一出口**：`turn_exit_gate` 单一写出口；`task_status` / `pending_kind` / 产品指标字段语义一致
- **可回归**：pytest 分层 + trace baseline + 核心 benchmark 不回退

### 1.2 当时刻意收窄的范围

- 不追求「所有材料类型一次齐」才交付
- 不承诺长期成长教练、全自动认知洞察
- 不把 Agent 编排本身当卖点，只验证「复杂信息任务能否被统一主链稳定处理」

### 1.3 MVP 最小闭环（历史口径）

- 一个统一主入口
- 一条稳定默认主路径 + 明确的复杂问题升级机制
- 统一结果出口 + 一组不会回退的核心验证指标

材料上 **优先用文档 / 网页 / 知识库** 打通「解析 → 当轮使用 → 用户确认后 commit → 检索复用」；视频与多来源 compare 可在 MVP 之后继续加厚（见 §2）。

---

## 2. 当前原型（已超过 MVP）— 现在时

**当前阶段是「可 demo 的原型」**，能力集 intentionally 大于 MVP。下列项与 `A1_publish` 代码 / 测试 / CI 一致（2026-06 口径）。

### 2.1 主链与 Agent

- 三 Agent 协作：Main → Middle → Answer（经 `application/chat/turn_orchestrator.py` 编排，`run_chat_turn.py` 仅为薄 facade；禁止 Agent 互调）
- Ingress：lane / `complex_candidate` / 初始 executor profile
- 门控：quality gate、feedback gate、approval gate（pending commit 闭环）
- 材料流：temporary / pending / committed；`material_flow` trace

### 2.2 材料与 Lane（可 demo）

| Lane | 典型能力 |
| --- | --- |
| `kb` | 混合检索（`RETRIEVAL_MODE=auto`）、KB 充分度、pending ingest |
| `document` | PDF/DOCX 等解析；大文档 / OCR 可 complex 或后台化 |
| `web` | 静态抓取；动态 / 反爬可 async |
| `video` | 字幕 probe、ASR 兜底、长视频可后台 task |
| `general` | 多来源 complex / compare |

### 2.3 异步与出口

- Async 控制面：排队 / worker / `task_id` + poll 终答
- 统一出口字段：`task_status`、`extra.pending_kind`、`insufficient_evidence`、`quality_gate_passed` 等（见 [10_用户可见状态文案](10_用户可见状态文案.md)）

### 2.4 评测与指标资产

- **8 类** trace baseline sample（`docs/current/baselines/samples/`）
- CI：覆盖率 ≥ 60%、migration/contract/smoke
- 产品指标 **v1**（`turn_product_metrics` + `aggregate_product_metrics.py`）
- 离线代表题：**6 条** sandbox（`scripts/metrics_sandbox_samples.yaml`）
- Agent eval / KB benchmark 目录与脚本

### 2.5 前端

- Next.js 代理 `/api-proxy/*`
- 主区摘要 `TurnStatusSummary` + 详版 `ContextRail`
- 用户可见文案治理：`frontend/lib/contextMeta/statusCopy.ts`（与 [10](10_用户可见状态文案.md) 对齐）

### 2.6 仍未当作「已成熟承诺」的能力

- 资料**二次调用率**等产品北极星（见 [04](04_产品指标看板.md)「建议补充」）
- 长期个人成长复盘 / 持续认知洞察（见 [02](02_简版PRD.md) 场景 4）
- 任意复杂问题的稳定深度分析（见 [03](03_用户场景与失败复盘.md) 风险节）

---

## 3. 下一阶段优先级（P0 / P1 / P2）— 将来时

评估维度：用户价值、主链稳定性、实现复杂度、验证效率、作品集表达。

### P0：必须先稳（主链与可信度）

- 路由与出口语义稳定（lane / mode / partial / pending 不「看起来像完成」）
- 统一质量门与单一事实源不回退
- 核心测试、trace baseline、OpenAPI 快照、CI 绿
- 产品指标 v1 字段与聚合口径不漂移

### P1：应该补强（闭环与可感知体验）

- **资料二次调用率**等北极星接线（PG / 导出 / 周报）
- commit / approval 专项 sandbox + 测试（见 [06](06_路由与能力测试矩阵.md) §6.4）
- `use_knowledge=true` 代表题固定进沙箱
- 前端：材料依据、异步状态、升级原因（文案 SSOT 已落 `statusCopy.ts`）
- 视频 / 网页 / 文档沉淀后的**继续追问**体验

### P2：继续加深（不是「还没做」）

- 视频链：质量、长视频、复盘体验优化
- 多来源 compare 更细分场景（网页+视频、已沉淀+外部等）
- 更细的多 Agent 策略与外部能力
- 运营向能力（配置后台、计费等）— 见 P3

### P3：当前不优先

- 商业化计费、多租户、企业后台、大规模运营自动化

---

## 4. 推荐演进路线（叙述用）

1. **MVP 阶段（已完成）**：验证统一主链命题（§1）
2. **原型阶段（当前）**：加厚 video / async / 指标 / 评测（§2）
3. **下一迭代**：按 §3 P0 → P1 → P2 收敛，不把 P2 写成「能力缺失」

一句话：

> A1 的 MVP 证明「复杂信息任务可以被统一主链处理」；当前原型证明「多条材料 lane + 门控 + 可评测」；下一步是在不夸大成熟度的前提下，把**沉淀复用**和**交付可信度**做厚。
