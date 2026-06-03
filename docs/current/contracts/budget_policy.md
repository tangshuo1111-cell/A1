# Budget Policy

> **Authority**: §15.7 of 平台图+三强自治核心架构迁移执行计划.md  
> **Code defaults**: `backend/config/budget_policy.py`

---

## Three-dimensional budget

Each active request carries a `BudgetSnapshot`:

| Dimension | Field | Unit |
|---|---|---|
| Wall-clock time | `budget_remaining_ms` | milliseconds |
| LLM API calls | `llm_calls_remaining` | count |
| Tool/capability calls | `tool_calls_remaining` | count |

---

## Default values per mode

| Mode | `budget_remaining_ms` | `llm_calls_remaining` | `tool_calls_remaining` |
|---|---|---|---|
| `fast` | 8 000 | 2 | 4 |
| `complex` | 45 000 | 12 | 20 |
| `async_per_task` | 600 000 (10 min) | 8 | 16 |

---

## Fuse rules (mandatory enforcement)

```
budget_remaining_ms <= 500   → stop sync path; finalize with current results
llm_calls_remaining == 0     → forbid further LLM autonomy; finalize / abort only
tool_calls_remaining == 0    → forbid further tool fallback; finalize with available material
round_index >= MAX_AUTONOMY_ROUNDS → stop_reason = "max_round_reached"
```

`MAX_AUTONOMY_ROUNDS = 4` (runtime constant in `config/budget_policy.py`)

---

## Accounting responsibility

| Layer | Injected by | Consumed by | Fuse enforced by |
|---|---|---|---|
| Sync main chain | `application/chat/budget_clock.py` | MiddleAgent / tool calls | `application/chat/run_chat_turn.py` |
| Autonomy loop | MainAgent | Middle / Answer | MainAgent |
| Async task | `tasks/orchestration/task_dispatcher` | worker | worker |

---

## Trace on every budget change

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

## Tests

```
tests/migration/test_budget_circuit.py
```

- Mock `llm_calls_remaining = 0` → assert no further LLM calls.
- Mock a capability with 9 s delay → assert fast lane finalises before 8 000 ms.
