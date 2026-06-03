# Ingress Router Plane

Request classification and lane/mode routing before chat turn execution.

Application layer must use `route_chat_request` from this package — not inline lane heuristics in `run_chat_turn`.

| Module | Role |
|---|---|
| `runtime.py` | `route_chat_request` 统一入口；组装 LaneDecision |
| `lane_selector.py` | lane 规则（video / document / web / kb / general） |
| `mode_selector.py` | fast vs complex 模式判定 |
| `request_classifier.py` | 轻量分类器与附件信号 |
| `semantic_router.py` | 语义路由 fallback |
| `lane_decision_schema.py` | `LaneDecision` Pydantic 契约 |

## Trace fields (required in prod)

- `request_id`, `lane`, `mode`, `router_source`, `router_confidence`
- Optional: `fast_lane_name`, `target_path` (P10 acceptance)

## Feature flags

- `ENABLE_INGRESS_ROUTER_V2` — 启用 v2 ingress（默认由 `ingress_router_active()` 读取）
- Kill switch: `ENABLE_OLD_UNIFIED_MAIN_CHAIN=True` 回退旧主链
