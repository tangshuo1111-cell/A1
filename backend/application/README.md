# backend/application

## Responsibilities

- 承接平台入口层编排，不直接代替 Agent 做主判断
- 负责请求进入系统后的顶层流程组织、模式切换、入口适配
- 作为「外层平台图」的应用入口层，与 `agents/` 的自治核心分层协作

## Boundary / What not to put here

- 不要把 `MainAgent / MiddleAgent / AnswerAgent` 的主判断逻辑重新写回这里
- 不要把具体视频处理、OCR、网页抓取、RAG 检索细节塞进这里
- 不要把 provider 细节、工具适配逻辑、存储细节放进这里
- 不要把共享能力平面实现放进这里，那些应进入 `services/`

## Owned entry points

| 路径 | 说明 |
|------|------|
| `application/chat/turn_orchestrator.py` | POST /chat/agno 唯一主链运行时入口 |
| `application/chat/run_chat_turn.py` | 薄 facade + 测试 monkeypatch 锚点（不得再增逻辑） |
| `application/ingress/` | lane/mode 初判；见 `ingress/README.md` |

## Files that must not keep growing

- `run_chat_turn.py` — 只保留参数整理与 `TurnOrchestrator.run()` 委托
- `executors/fast_lanes/*_fast_impl.py` — 各 lane 执行体；`fast_common.py` 共享 LLM/白名单
- `pipeline/turn_pipeline.py` — 阶段编排；业务细节不得回流 orchestrator

主链技术说明：`application/chat/README.md`
