# backend/agents

## Responsibilities

- 承载三强自治核心，是系统的“大脑层”
- 保留 `MainAgent / MiddleAgent / AnswerAgent` 的主判断权
- 负责复杂模式下的规划、能力编排、证据验证、最终签字
- 为后续 `Complex Lane` 和自治闭环提供稳定主入口

## Result 契约

| 类型 | 职责 | 禁止写入 |
|------|------|----------|
| `MainAgentResult` | 协作规划 `plan` | `ok`, `task_id`, `workflow_elapsed_ms`, `http_status`, `primary_path`, `route_response_flags`, `task_status` |
| `MiddleAgentResult` | 材料 `bundle` + `MaterialGateFacts` | 同上 |
| `AnswerAgentResult` | `answer_text` + `huida_pan` + `agent_extra`（仅 v6_*） | 同上 |

编排层通过 `agents/ports.py` 调用；HTTP 顶层字段只由 `application/chat/turn_response_builder.py` 写入。

## Boundary / What not to put here

- 不要把入口层语义路由器直接实现为 Agent 目录内公共杂糅逻辑
- 不要 import FastAPI / 不要写 turn 级 HTTP 响应字段
- 不要把 provider 细节、具体 OCR/ASR/抓取细节放在 agent 中
- 不要把 queue backend、worker runtime、数据库访问细节放进这里
- 不要让 agent 文件继续承担大块工具适配或重处理核心

## Owned files

- `backend/agents/main_agent/`
- `backend/agents/middle_agent/`
- `backend/agents/answer_agent/`
- `backend/agents/multisource/`
- `backend/agents/shared/`
- `backend/agents/_runtime.py`
- `backend/agents/agno_chat_agent.py`
- `backend/agents/evidence_normalizer.py`
- `backend/agents/history_context.py`

## Files that must not keep growing

- `backend/agents/middle_agent/video_flow.py`
  只应保留 Middle 的视频编排入口，不应继续承载切段、并发 ASR、后台任务调度等重处理核心。
- `backend/agents/main_agent/main_invoke_flow.py`
  应继续聚焦复杂模式规划与决策，不应继续吸收底层能力实现。
- `backend/agents/answer_agent/runtime.py`
  应继续聚焦验证与签字，不应承接材料抓取或能力编排。
