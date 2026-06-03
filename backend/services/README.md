# backend/services

## Responsibilities

- 承载共享能力平面，是系统的“能力层”
- 提供视频、文档、网页、知识能力的服务化封装
- 提供同步执行策略、反馈门控、后台任务承接等中间服务
- 为 `application/` 和 `agents/` 提供可复用的能力入口，而不是主判断中心

## Boundary / What not to put here

- 不要把 `MainAgent / MiddleAgent / AnswerAgent` 的主判断重新下沉到这里
- 不要把 HTTP 路由逻辑、请求体验逻辑塞进这里
- 不要把 worker entry、队列消费循环、平台状态机直接实现在这里
- 不要继续维持根目录平铺增长，后续能力应收敛到 `services/capabilities/*`

## Owned files

- `backend/services/agno_chat_service.py`
- `backend/services/agno_rag_service.py`
- `backend/services/agno_web_service.py`
- `backend/services/feedback_gate.py`
- `backend/services/ingest_service.py`
- `backend/services/pending_ingestion_service.py`
- `backend/services/session_store.py`
- `backend/services/task_query_service.py`
- `backend/services/task_trace_cache.py`
- `backend/services/video_audio_service.py`
- `backend/services/video_parallel_asr_service.py`
- `backend/services/video_processing_service.py`
- `backend/services/video_segment_service.py`
- 未来预留：
  - `backend/services/capabilities/video/`
  - `backend/services/capabilities/document/`
  - `backend/services/capabilities/web/`
  - `backend/services/capabilities/knowledge/`
  - `backend/services/execution/`

## Files that must not keep growing

- `backend/services/agno_chat_service.py`
  只应保留 service facade，不应继续吸收 lane 决策与主链重判断。
- `backend/services/` 根目录平铺结构
  新能力不应继续直接平铺在根目录，后续统一进入 capability / execution 子平面。
