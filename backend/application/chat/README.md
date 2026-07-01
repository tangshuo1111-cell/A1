# chat 主链

POST /chat/agno 的唯一编排目录。路由与 gate 决策在此收敛；Agent 与 capability 只被调用。

## 入口

```
chat_agno → agno_chat_service → run_chat_turn (facade) → turn_orchestrator.run()
```

## 三对象 + 状态机

| 对象 | 文件 | 职责 |
|------|------|------|
| `TurnContext` | `domain/context.py` | request/session/upload/pending/flags |
| `TurnDecision` | `domain/decision.py` | lane/mode/primary_path/reason_codes |
| `TurnRuntimeState` | `domain/runtime_state.py` | 状态迁移轨迹 |
| `TurnExecutionResult` | `domain/execution_result.py` | executor 统一返回 |
| 状态机 | `turn_state_machine.py` | **唯一**写入 `TurnDecision.mode` |

Gate 只产 `TurnEvent` → `apply_event`；禁止 gate 直接改 mode。

## Executors

| Executor | 职责 |
|----------|------|
| `FastExecutor` | fast lane + delivery_gate；不升 complex 决策 |
| `ComplexExecutor` | Main → Middle → Answer + feedback round |
| `AsyncExecutor` | 入队 task；不调三 Agent |

Lane 实现：`executors/fast_lanes/{kb,web,video,document,general}.py`

## Gates → Events

```
approval_gate → blocked / commit_executed / continue
decision_arbitrator → mode_arbitrated
fast_lane_gate → fast_rejected / continue
delivery_gate → completed / upgrade_profile / need_second_round
```

## Field owners

顶层 HTTP 字段只在 `turn_response_builder.py` 写入（见 `field_owners.py`）。
前置阶段允许写入 `extra.*` 候选信号用于路由 / trace / 兼容拼装，但这些值不是最终公开事实；最终对外 `task_status / primary_path / mode / pending_kind / executor_profile / router_lane` 统一由 `turn_exit_gate -> turn_response_builder` 覆盖。
兼容镜像字段由 `turn_response_builder.merge_compat_fields()` 处理。

## 材料生命周期

```
prepare → pending_commit → commit → committed
         ↘ discard / failed
```

`prepare` 不入库；`commit` 只经 `pending_ingestion_service`；上层传 `pending_id`。

## 知识调用

业务检索/入库/pending 唯一入口见 `backend/services/capabilities/knowledge/README.md`。

## 主链简图

```
ingress → approval_gate → arbitrator → shared_material_prep
  → async? → return
  → FastExecutor? → delivery_gate → return | fall-through
  → ComplexExecutor (Main → Middle → Answer [→ feedback round])
  → turn_exit_gate → turn_response_builder
```

## 禁止事项

1. 新逻辑不得进入 `run_chat_turn.py`；fast lane 逻辑在 `executors/fast_lanes/`
2. Agent 不得写 `mode` / `primary_path` / `workflow_elapsed_ms`
3. `application/*` / `agents/*` 禁止直连 `rag.*`（走 `retrieve_service`）
4. 主路径禁止 `import backend.compat.*`（测试除外）
5. executor 内禁止 `HTTPException` / 裸 `JSONResponse`

## 参考

- 规则细节：`docs/current/04_默认路由_材料流与质量门控规则.md`
- Ingress：`backend/application/ingress/README.md`
- 契约测试：`tests/backend/application/chat/`、`tests/migration/test_round*.py`
