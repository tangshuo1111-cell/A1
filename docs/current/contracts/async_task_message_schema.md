# AsyncTaskMessage Schema

> **Authority**: §15.4.3 of 平台图+三强自治核心架构迁移执行计划.md  
> **Version**: 1  
> **Delivery semantics**: `at_least_once` (idempotency key: `task_id`)

---

## Schema

```yaml
schema: AsyncTaskMessage
version: 1
required:
  - task_id
  - task_type
  - lane
  - source_type
  - source_ref
  - request_id
  - payload_version
  - retry_count
  - status
  - enqueued_at_ms
optional:
  - session_id
  - priority
  - parent_task_id
  - deadline_ms
  - last_error
  - result_ref
fields:
  task_id:
    type: string
    pattern: "^task_[a-zA-Z0-9_]{6,}$"
  task_type:
    type: enum
    values: ["video_asr_background", "document_ocr", "web_heavy_fetch", "multi_source_research"]
  optional_task_types:
    description: "Accepted in schema/enqueue but not fully implemented on async plane"
    values: ["multi_source_research"]
    handler: "async_dispatcher marks failed with error_code=multi_source_research_optional"
  lane:
    type: enum
    values: LANE
  source_type:
    type: enum
    values: ["web_video", "local_video", "web_page", "document", "kb", "mixed"]
  source_ref:
    type: string
  request_id:
    type: string
  session_id:
    type: string
    default: ""
  payload_version:
    type: int
    default: 1
  retry_count:
    type: int
    min: 0
    max: 5
  priority:
    type: enum
    values: ["high", "normal", "low"]
    default: "normal"
  status:
    type: enum
    values: TASK_STATUS
  parent_task_id:
    type: string
    default: ""
  deadline_ms:
    type: int
    default: 0
  last_error:
    type: string
    default: ""
  result_ref:
    type: string
    default: ""
  enqueued_at_ms:
    type: int
```

---

## Result response schema (`GET /tasks/{id}/result`)

```yaml
required:
  - task_id
  - status
  - payload_version
optional:
  - data
  - error_code
  - error_message
  - finished_at_ms
```

---

## Task status state machine

See `enums.md` → `TASK_STATUS` for legal transitions.

---

## Example (positive)

```yaml
task_id: "task_001"
task_type: "video_asr_background"
lane: "video"
source_type: "web_video"
source_ref: "https://example.com/v"
request_id: "req_abc123"
session_id: "sess_001"
payload_version: 1
retry_count: 0
priority: "normal"
status: "pending"
enqueued_at_ms: 1716297600000
```

## Example (negative — must reject)

```yaml
task_id: "t1"                  # too short, no task_ prefix
task_type: "image_analysis"    # not in allowed task_types
status: "queued"               # not in TASK_STATUS
retry_count: 10                # exceeds max
```

---

## Compatibility constraints

- `payload_version` MUST be incremented for any breaking payload change.
- Old clients that do not read new fields MUST still parse successfully.
- `task_id` uniqueness is the caller's responsibility.
