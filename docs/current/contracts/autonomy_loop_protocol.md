# Autonomy Loop Protocol (AutonomyLoopEvent Schema)

> **Authority**: §15.4.2 of docs/history/current/平台图+三强自治核心架构迁移执行计划.md  
> **Version**: 1  
> **Implementation**: `backend/application/chat/autonomy_loop.py`

---

## Schema

```yaml
schema: AutonomyLoopEvent
version: 1
required:
  - loop_id
  - round_index
  - trigger
  - requested_action
  - requested_by
  - budget_snapshot
optional:
  - stop_reason
  - payload
  - emitted_at_ms
fields:
  loop_id:
    type: string
    pattern: "^loop_[a-zA-Z0-9_]{6,}$"
  round_index:
    type: int
    min: 0
    max: 8     # hard ceiling; runtime constant MAX_AUTONOMY_ROUNDS = 4 (config/budget_policy.py)
  trigger:
    type: enum
    values: AUTONOMY_TRIGGER
  requested_action:
    type: enum
    values: REQUESTED_ACTION
  requested_by:
    type: enum
    values: ["MainAgent", "MiddleAgent", "AnswerAgent"]
  budget_snapshot:
    budget_remaining_ms:
      type: int
    llm_calls_remaining:
      type: int
    tool_calls_remaining:
      type: int
  stop_reason:
    type: enum
    values: STOP_REASON
    default: ""
  payload:
    type: object
    default: {}
  emitted_at_ms:
    type: int
    default: 0
```

---

## trigger → allowed requested_action matrix

| trigger | allowed requested_actions |
|---|---|
| `initial_dispatch` | `continue_same_plan` |
| `insufficient_evidence` | `more_video_material`, `more_document_material`, `more_web_material`, `more_kb_material`, `replan`, `escalate_to_complex`, `escalate_to_async`, `abort_and_finalize` |
| `answer_quality_low` | `replan`, `continue_same_plan`, `escalate_to_complex`, `abort_and_finalize` |
| `tool_failure` | `continue_same_plan`, `replan`, `escalate_to_async`, `abort_and_finalize` |
| `fallback_provider_required` | `continue_same_plan` |
| `user_clarification_needed` | `abort_and_finalize` |
| `internal_error` | `abort_and_finalize` |

---

## Sequence contract (v1: sequential loop only)

```
MainAgent → MiddleAgent → AnswerAgent → MainAgent → …
```

- Maximum `round_index`: `MAX_AUTONOMY_ROUNDS` (default 4).  
- When `round_index >= MAX_AUTONOMY_ROUNDS`, `stop_reason` MUST be `max_round_reached`.
- Event-driven second version is out of scope for P8.

---

## Example (positive)

```yaml
loop_id: "loop_001"
round_index: 1
trigger: "insufficient_evidence"
requested_action: "more_video_material"
requested_by: "AnswerAgent"
budget_snapshot:
  budget_remaining_ms: 8200
  llm_calls_remaining: 4
  tool_calls_remaining: 6
stop_reason: ""
```

## Example (negative — must reject)

```yaml
loop_id: "x"                    # too short
trigger: "unknown_trigger"      # not in AUTONOMY_TRIGGER
requested_action: "switch_to_async"   # retired value
round_index: -1                 # below min
```
