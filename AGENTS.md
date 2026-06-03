# AGENTS.md — 项目 Agent 架构说明

## 三层 Agent 协作

```
用户消息 → MainAgent → MiddleAgent → AnswerAgent → 最终回答
```

### MainAgent（主路由）

- 职责：判断用户意图，决定走哪条路径（直接回答 / 需要工具 / 需要检索）
- 位置：`backend/agents/main_agent/`
- 关键文件：`runtime.py`（入口）、`main_invoke_flow.py`（路由状态机）

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

---

## 规则

- 不允许 Agent 之间直接互相调用（必须通过编排层）
- 不允许工具层访问 Agent 状态
- 配置集中在 `backend/config/`
- 成本规则：`config/cost_rule.py`
- 安全规则：`config/safe_rule.py`
