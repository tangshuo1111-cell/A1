# Trace Field Catalog

> **Authority**: §15.6 of docs/history/current/平台图+三强自治核心架构迁移执行计划.md  
> **Implementation**: HTTP metrics `backend/observability.py` + `api/routes/internal_observability.py`（`GET /internal/metrics`）；phase 日志 `backend/core/observability.py`；chat exit trace `turn_response_builder.py` / `exit_extra_builder.py` / `response_assembly.py`  
> **Forbidden**: Do NOT create a second trace framework.

---

## Field level definitions

| Level | Meaning |
|---|---|
| **PROD** | Must be emitted in production environments |
| **DEBUG** | Only emitted when debug tracing is enabled |

---

## Ingress Router Trace

| Field | Level | Type | Source |
|---|---|---|---|
| `request_id` | PROD | string | `application/ingress` |
| `router_lane` | PROD | enum LANE | exit extra canonical 键（`field_owners.py`）；同值同时镜像为 `lane` |
| `mode` | PROD | enum MODE | same |
| `router_source` | PROD | enum ROUTER_SOURCE | same |
| `router_confidence` | PROD | float | same |
| `router_fallback` | DEBUG | bool | same |
| `router_decision_ms` | DEBUG | int | same |

---

## Fast Lane Trace

| Field | Level | Type |
|---|---|---|
| `fast_lane_name` | PROD | enum LANE |
| `capabilities_called` | PROD | list[string] |
| `cross_lane_violation` | PROD | bool |
| `fast_exit_reason` | PROD | string |
| `fast_first_response_ms` | PROD | int |

---

## Three-Agent Autonomous Core Trace

| Field | Level | Type |
|---|---|---|
| `loop_id` | PROD | string |
| `round_index` | PROD | int |
| `main_decision` | PROD | enum REQUESTED_ACTION |
| `middle_action` | DEBUG | string |
| `answer_check` | PROD | enum {"pass","revise","more_evidence"} |
| `revise_requested` | PROD | bool |
| `retry_requested` | PROD | bool |
| `more_evidence_requested` | PROD | bool |
| `stop_reason` | PROD | enum STOP_REASON |
| `loop_total_rounds` | PROD | int |

---

## Async Control Plane Trace

| Field | Level | Type |
|---|---|---|
| `task_id` | PROD | string |
| `task_type` | PROD | string |
| `task_status` | PROD | enum ASYNC_TASK_STATUS |
| `queue_backend` | PROD | enum QUEUE_BACKEND |
| `worker_id` | DEBUG | string |
| `retry_count` | PROD | int |
| `task_enqueue_to_finish_ms` | PROD | int |
| `result_status` | PROD | enum {"succeeded","failed","timeout"} |

---

## Performance Trace

| Field | Level | Type |
|---|---|---|
| `first_response_ms` | PROD | int |
| `total_ms` | PROD | int |
| `provider_ms` | DEBUG | dict[provider→ms] |
| `capability_ms` | DEBUG | dict[capability→ms] |
| `answer_ms` | DEBUG | int |
| `llm_calls` | PROD | int |
| `tool_calls` | PROD | int |
| `token_in` | PROD | int |
| `token_out` | PROD | int |

---

## Budget delta trace (emitted on every budget change)

```json
{
  "budget.delta": {
    "ms": -1240,
    "llm": -1,
    "tool": 0,
    "reason": "<capability_name>"
  }
}
```

---

## Product Metrics v1（`turn_exit_gate` 统一写入）

| Field | Level | Type | Source |
|---|---|---|---|
| `quality_gate_passed` | PROD | bool | `turn_response_builder.build_exit_extra_from_envelope`（exit gate 触发；旧 `envelope_to_extra_fields` 已 deprecated 并转发至此） |
| `insufficient_evidence` | PROD | bool | same |
| `is_complex_task` | PROD | bool | same |
| `failure_reason_code` | PROD | string | same |
| `timing_total_ms` | PROD | int | same（apply_turn_exit 补写） |
| `answer_char_count` | PROD | int | same |

---

## Validation

```
tests/migration/test_trace_contract.py
```

Load each baseline sample, run through the new path, assert all PROD fields are
present and all enum values are within legal sets.
