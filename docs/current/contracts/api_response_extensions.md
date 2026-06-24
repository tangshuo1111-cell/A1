# API Response Extensions

> **Authority**: §15.11 of docs/history/current/平台图+三强自治核心架构迁移执行计划.md  
> **Also see**: `backend/api/routes/chat_agno.py`、`docs/current/openapi.json`

---

## Affected endpoints

| Endpoint | Current purpose | Migration change |
|---|---|---|
| `POST /chat/agno` | Synchronous Q&A main entry | 顶层 canonical：`task_status`（`pending\|succeeded\|failed\|blocked\|partial`）、`primary_path`；`extra` 含 `router_lane`、`mode`、`router_source`、`loop_total_rounds` 等（canonical 键为 `router_lane`，compat 可能仍镜像 `lane`） |
| `GET /tasks/{id}` | Task status query | `status` 用 **ASYNC_TASK_STATUS**（§enums.md，含 `queued`/`expired`/`cancelled` 等） |
| `GET /tasks/{id}/result` | Task result | Adds `payload_version` field; old clients may ignore it |
| `POST /ingest/*` | Ingestion | No change |
| `GET /sessions/*` | Session | No change |

---

## `POST /chat/agno` — new optional response fields

```json
{
  "ok": true,
  "answer": "...",
  "task_status": "succeeded",
  "primary_path": "fast_video",
  "extra": {
    "router_lane": "video",
    "mode": "fast",
    "router_source": "rule",
    "router_confidence": 0.93,
    "loop_total_rounds": 0
  }
}
```

> chat 顶层 `task_status` canonical 取值：`pending | succeeded | failed | blocked | partial`（`blocked` = approval gate 阻断，前端文案「已阻止」）。`extra` 路由字段 canonical 键为 `router_lane`。

All new fields are **optional**. Old clients that do not read them continue to work.

---

## `GET /tasks/{id}` — status field (async, canonical)

| Value | Meaning |
|---|---|
| `"pending"` | Accepted, not yet running |
| `"queued"` | 已入队（`task_query_service.normalize_public_task_status` 仍公开返回） |
| `"running"` | Worker is executing |
| `"succeeded"` | Terminal success |
| `"failed"` | Terminal failure |
| `"partial"` | Partial result within SLA (complex / multisource) |
| `"expired"` / `"cancelled"` / `"timeout"` / `"resumed"` | 见 enums.md ASYNC_TASK_STATUS |

> 注：async 任务面与 chat 轮次面 `task_status` 是**两套枚举**（chat 含 `blocked`，async 含 `queued`/`expired`）；以 `backend/services/task_plane/task_query_service.py` 与 `chat_contracts.py` 为代码真源。

---

## `GET /tasks/{id}/result` — new field

```json
{
  "task_id": "task_001",
  "status": "succeeded",
  "payload_version": 1,
  "data": { ... }
}
```

---

## Compatibility constraints

1. New fields MUST be **optional** — old clients must not break.
2. Existing field types MUST NOT change.
3. Old fields MUST NOT be deleted before 2 phases after introduction.

---

## Tests

```
tests/migration/test_api_contract.py
```

Each endpoint has both an "old client" and "new client" fixture.
Old client MUST still parse successfully.
