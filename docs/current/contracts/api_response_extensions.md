# API Response Extensions

> **Authority**: §15.11 of docs/history/current/平台图+三强自治核心架构迁移执行计划.md  
> **Also see**: `backend/api/README.md`

---

## Affected endpoints

| Endpoint | Current purpose | Migration change |
|---|---|---|
| `POST /chat/agno` | Synchronous Q&A main entry | Response body gains optional fields: `lane`, `mode`, `router_source`, `loop_total_rounds` |
| `GET /tasks/{id}` | Task status query | `status` uses TASK_STATUS enum (§enums.md); canonical values only after S11 |
| `GET /tasks/{id}/result` | Task result | Adds `payload_version` field; old clients may ignore it |
| `POST /ingest/*` | Ingestion | No change |
| `GET /sessions/*` | Session | No change |

---

## `POST /chat/agno` — new optional response fields

```json
{
  "ok": true,
  "answer": "...",
  "extra": {
    "lane": "video",
    "mode": "fast",
    "router_source": "rule+light_classifier",
    "router_confidence": 0.93,
    "loop_total_rounds": 0
  }
}
```

All new fields are **optional**. Old clients that do not read them continue to work.

---

## `GET /tasks/{id}` — status field (canonical)

| Value | Meaning |
|---|---|
| `"pending"` | Accepted, not yet running |
| `"running"` | Worker is executing |
| `"succeeded"` | Terminal success |
| `"failed"` | Terminal failure |
| `"partial"` | Partial result within SLA (complex / multisource) |

Legacy aliases `"queued"` and `"in_progress"` were removed in S11; clients MUST use the values above.

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
