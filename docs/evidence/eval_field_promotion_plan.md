# 评测字段晋升计划

目的：先盘点哪些评测信号已经是当前代码现实里的稳定出口字段，哪些仍然只是脆弱观测或评测侧推导，避免把 fragile 信号误升成 hard 契约。

## 当前判定口径

| 字段 | 当前档位 | 代码证据 | 是否建议晋升 | 说明 |
| --- | --- | --- | --- | --- |
| `commit_status` | `stable_result` | `backend/rag/pending_schema.py`、`backend/application/chat/material_lifecycle.py`、`tests/evaluation/runners/eval_state_extractors.py` | 是 | 已有明确 commit 生命周期语义，适合做保存类诚实性规则的稳定信号。 |
| `kb_hits` / `kb_hit_count` | `stable_result` | `backend/application/chat/shared_material_prep.py`、`backend/application/chat/executors/fast_lanes/kb_fast_impl.py`、`tests/evaluation/runners/eval_agent_extractors.py` | 是 | 已在 fast / shared material 两侧稳定产出，适合做 KB grounding 基线。 |
| `background_task_id` | `stable_result` | `backend/application/chat/chat_contracts.py`、`backend/application/chat/turn_facts.py`、`backend/application/chat/pipeline/complex_finalize_stage.py` | 是 | 已有统一解析与提升逻辑，可作为后台任务存在性的稳定信号。 |
| `web_primary_source` | `contextual` | `backend/services/capabilities/web/web_orchestration_service.py`、`tests/evaluation/runners/eval_capability_extractors.py` | 条件晋升 | 当前在 web 相关链路可稳定观测，但不是所有出口的公共契约，不宜升成全局 hard 字段。 |
| `transcript_source` | `contextual` | `backend/application/chat/response_assembly.py`、`backend/services/capabilities/video/processing_service.py`、`tests/evaluation/runners/eval_capability_extractors.py` | 条件晋升 | 当前在 video 链路可稳定观测，但仍属场景化信号。适合 video 规则读取，不宜要求所有请求具备。 |
| `has_previous_steps` | 评测推导 | `tests/evaluation/runners/eval_state_extractors.py` | 否 | 这是评测 runner 根据前序步骤推导出的闭环信号，不是业务出口字段，禁止晋升。 |
| `quality_gate.reason_codes` | `fragile_observability` | `backend/application/chat/response_builders/exit_extra_builder.py`、`tests/evaluation/runners/eval_field_catalog.py` | 暂不晋升 | 当前适合辅助 warning / insufficiency 证据，不宜单独充当 hard 契约。 |

## 晋升原则

1. 能从统一出口稳定读到，且不是 runner 推导值，才允许晋升。
2. 场景化字段可以作为 `contextual` 或 `stable_result` 使用，但不自动升级为“所有请求都必须存在”的全局契约。
3. 纯 `extra.v6_* / v15_* / trace*` 观测字段默认不晋升。
4. `has_previous_steps`、`answer_mentions_previous` 这类评测推导值只能做 checker 辅助，不能回写成业务 contract。

## 当前结论

- 已晋升：`commit_status`、`kb_hits` / `kb_hit_count`、`background_task_id`
- 保持场景稳定：`web_primary_source`、`transcript_source`
- 明确不晋升：`has_previous_steps`
