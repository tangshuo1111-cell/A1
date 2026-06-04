# AGENTS.md — 项目 Agent 架构说明

## 三层 Agent 协作

三层 Agent 协作只完整存在于 `complex` 主链中，不代表所有请求的默认运行顺序。

更贴近当前代码现实的口径是：

```
POST /chat/agno
→ ingress（lane / mode / complex_candidate）
→ approval_gate
→ decision_arbitrator
→ shared_material_prep
→ fast / complex / async
→ （complex 时）MainAgent → MiddleAgent → AnswerAgent
→ turn_exit_gate
```

### MainAgent（复杂链协作起点）

- 职责：在 `complex` 主链里负责协作方向、任务规划和复杂任务处理起点
- 位置：`backend/agents/main_agent/`
- 关键文件：`runtime.py`（入口）、`main_invoke_flow.py`（路由状态机）

说明：
- 入口初始 `lane / mode` 不只由 MainAgent 决定
- 当前默认入口初判在 `backend/application/ingress/`

### MiddleAgent（中间执行）

- 职责：执行工具调用、检索知识、收集多来源材料、组装证据包
- 位置：`backend/agents/middle_agent/`
- 关键文件：`runtime.py`（入口）、`gather_phase.py`（收集阶段）、`judgment_phase.py`（判断阶段）

### AnswerAgent（最终生成）

- 职责：基于收集到的材料，生成最终回答
- 位置：`backend/agents/answer_agent/`
- 关键文件：`runtime.py`（入口）

---

## 编排入口

- **API 层**：`backend/api/routes/chat_agno.py` → `POST /chat/agno`
- **Service 层**：`backend/services/agno_chat_service.py`（monkeypatch 锚点）
- **Implementation**：`backend/application/chat/run_chat_turn.py`（真正的编排逻辑）

补充：
- 统一公共出口：`backend/application/chat/turn_exit_gate.py`
- 统一材料层语义：`backend/application/chat/material_flow.py`
- 统一资料生命周期：`backend/services/capabilities/knowledge/pending_ingestion_service.py`

---

## 工具体系

位于 `backend/tools/`：

| 工具 | 目录 | 说明 |
|------|------|------|
| 文档解析 | `tools/document/` | PDF/DOCX/XLSX/TXT |
| 网页搜索 | `tools/search/` | DuckDuckGo / Tavily |
| 网页抓取 | `tools/web/` | 静态 + 动态(Playwright) |
| 视频处理 | `tools/video/` | 字幕提取、ASR |
| ASR | `tools/asr/` | 语音转写 |

---

## 知识库（RAG）

- 位置：`backend/rag/`
- 核心：`retriever.py`（检索）、`ingest.py`（入库）、`hybrid_retrieve.py`（混合检索）

当前知识沉淀口径：
- `prepare` 只解析、不入库
- 用户明确要求保存后才 `commit`
- 入库后再通过 retrieval 命中

---

## 规则

- 不允许 Agent 之间直接互相调用（必须通过编排层）
- 不允许工具层访问 Agent 状态
- 配置集中在 `backend/config/`
- 成本规则：`config/cost_rule.py`
- 安全规则：`config/safe_rule.py`

当前对外表达时要避免的误导：
- 不要把整个系统写成 `用户 -> Main -> Middle -> Answer`
- 不要把 `async` 写成默认路径，它是少数重任务的后台兜底出口
- 不要把“抓到内容”写成“自动入库”，当前是先处理、后保存、再 commit
