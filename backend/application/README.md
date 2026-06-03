# backend/application

## Responsibilities

- 承接平台入口层编排，不直接代替 Agent 做主判断
- 负责请求进入系统后的顶层流程组织、模式切换、入口适配
- 未来承接 `Semantic Router`、`lane` 选择、`mode` 选择、平台级入口编排
- 作为“外层平台图”的应用入口层，与 `agents/` 的自治核心分层协作

## Boundary / What not to put here

- 不要把 `MainAgent / MiddleAgent / AnswerAgent` 的主判断逻辑重新写回这里
- 不要把具体视频处理、OCR、网页抓取、RAG 检索细节塞进这里
- 不要把 provider 细节、工具适配逻辑、存储细节放进这里
- 不要把未来的共享能力平面实现放进这里，那些应进入 `services/`

## Owned files

- `backend/application/chat/run_chat_turn.py`
- `backend/application/chat/__init__.py`
- 未来预留：
  - `backend/application/ingress/semantic_router.py`
  - `backend/application/ingress/lane_selector.py`
  - `backend/application/ingress/mode_selector.py`
  - `backend/application/ingress/request_classifier.py`

## Files that must not keep growing

- `backend/application/chat/run_chat_turn.py`
  只应保留顶层请求编排、模式切换、响应组装，不应继续吸收 lane 决策、重处理实现、能力细节。
