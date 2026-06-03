# Enums — Canonical Definitions

> **Authority**: §15.3 of 平台图+三强自治核心架构迁移执行计划.md  
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

```
ROUTER_SOURCE = {
  "rule",                   # high-confidence rule hit
  "light_classifier",       # lightweight classifier hit
  "rule+light_classifier",  # both agree
  "llm_router",             # LLM router decision
  "main_agent_escalation",  # escalated to MainAgent
  "fallback_default"        # all classifiers failed
}
```

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

## TASK_STATUS（state machine）

```
TASK_STATUS = {
  "pending",    # enqueued, not yet consumed
  "running",    # worker processing
  "succeeded",
  "failed",
  "timeout",
  "cancelled",
  "resumed"     # restarted after interruption
}
```

**Legal transitions:**
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
