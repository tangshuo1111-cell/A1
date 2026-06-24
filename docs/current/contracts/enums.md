# Enums — Canonical Definitions

> **Authority**: §15.3 of docs/history/current/平台图+三强自治核心架构迁移执行计划.md  
> All protocol fields MUST use these enums. Any change requires a plan-doc update first.

---

## LANE（5 values, closed enum）

```
LANE = { "video", "document", "web", "kb", "general" }
```

## MODE（3 values, closed enum）

```
MODE = { "fast", "complex", "async" }
```

> `async`: first response only creates a task + status acknowledgement.
> Backend worker handles heavy processing. `LaneDecision.mode = "async"` MUST
> produce a corresponding `AsyncTaskMessage`.

## ROUTER_SOURCE（closed enum）

代码真源 `backend/application/ingress/lane_decision_schema.py` 的 `RouterSourceName`：

```
ROUTER_SOURCE = {
  "rule",              # high-confidence rule hit
  "light_classifier",  # lightweight classifier hit
  "main_agent"         # escalated / decided by MainAgent
}
```

> 历史口径中出现过 `rule+light_classifier` / `llm_router` / `main_agent_escalation` / `fallback_default` 等字符串，**非当前 ingress 产出**，仅可能存在于旧 trace / compat 镜像，不得作为 canonical。

## AUTONOMY_TRIGGER（closed enum）

```
AUTONOMY_TRIGGER = {
  "initial_dispatch",
  "insufficient_evidence",
  "answer_quality_low",
  "tool_failure",
  "fallback_provider_required",
  "user_clarification_needed",
  "internal_error"
}
```

## REQUESTED_ACTION（closed enum）

```
REQUESTED_ACTION = {
  "continue_same_plan",
  "replan",
  "more_video_material",
  "more_document_material",
  "more_web_material",
  "more_kb_material",
  "escalate_to_complex",    # fast → complex upgrade
  "escalate_to_async",      # complex → async upgrade
  "downgrade_to_fast",
  "abort_and_finalize"
}
```

## STOP_REASON（closed enum）

```
STOP_REASON = {
  "answer_signed_off",
  "max_round_reached",
  "time_budget_exhausted",
  "llm_budget_exhausted",
  "tool_budget_exhausted",
  "unrecoverable_error",
  "user_cancelled"
}
```

## TASK_STATUS（两套语义，勿混用）

公开出口有两个不同的 task_status 面，**取值集合不同**：

### CHAT_TURN_TASK_STATUS（`POST /chat/agno` 顶层 + extra）

代码真源 `backend/application/chat/chat_contracts.py::TurnExitTaskStatus`：

```
CHAT_TURN_TASK_STATUS = {
  "pending",
  "succeeded",
  "failed",
  "blocked",    # approval gate 阻断（前端文案「已阻止」）
  "partial"     # 部分完成
}
```

> 业务/前端读 chat 轮次状态时以本集合为准（含 `blocked` / `partial`）。`done` / `completed` / `routed` 会被 `normalize_task_status` 归一到 `succeeded`。

### ASYNC_TASK_STATUS（异步任务生命周期，`GET /tasks*`）

```
ASYNC_TASK_STATUS = {
  "pending",    # enqueued, not yet consumed
  "queued",     # 公开镜像（task_query_service.normalize_public_task_status 仍返回）
  "running",    # worker processing
  "succeeded",
  "failed",
  "partial",
  "timeout",
  "expired",
  "cancelled",
  "resumed"     # restarted after interruption
}
```

**Async legal transitions:**
```
pending  → running | cancelled
running  → succeeded | failed | timeout | resumed
resumed  → running
failed   → running  (only if retry_count < max_retry)
timeout  → running  (same condition)
succeeded / cancelled → terminal
```

## QUEUE_BACKEND（closed enum）

```
QUEUE_BACKEND = { "memory", "redis" }
```

## DELIVERY_SEMANTICS

```
DELIVERY_SEMANTICS = { "at_least_once" }   # platform-level mandate
```

> Complex task results are idempotent via `task_id`. Business layer MUST read
> `task_status` rather than relying on single-delivery.
