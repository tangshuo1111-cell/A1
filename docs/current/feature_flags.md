# Feature Flags 清单

位置：`backend/config/feature_flags.py`  
**Phase 2**：env 覆盖（当前仅代码内默认值 + 测试 monkeypatch）。

| Flag | 默认 | 作用 |
| --- | --- | --- |
| `ENABLE_INGRESS_ROUTER_V2` | true | Ingress 路由 v2 |
| `ENABLE_FAST_LANE_*` | true | 各 lane fast path（video/document/web/kb/general） |
| `ENABLE_THREE_AGENT_AUTONOMY` | true | Complex Main→Middle→Answer 闭环 |
| `ENABLE_ASYNC_CONTROL_PLANE_V2` | true | 统一 async 任务平面 |
| `ENABLE_MAIN_PLAN_CACHE` | true | Main plan 缓存 |
| `ENABLE_BUDGET_CLOCK_V2` | true | 同步 SLA 预算 |
| `ENABLE_DECISION_ARBITRATOR` | true | mode 仲裁 |
| `ENABLE_FAST_LANE_GATE` | true | session pending 时拒 fast |
| `ENABLE_CAPABILITY_FACT_*` | true | 各 capability 契约事实 |
| `ENABLE_QUALITY_GATE` | true | 质量门控 |
| `ENABLE_SHARED_RETRIEVAL` | true | fast/complex 共享 KB 检索 |
| `ENABLE_KB_SUFFICIENCY_GATE` | true | KB 充分度 |
| `ENABLE_APPROVAL_GATE_V1` | true | 用户确认 / commit |
| `ENABLE_TURN_EXIT_GATE_SHADOW` | false | 出口 shadow 对比（默认关） |
| `ENABLE_STRUCTURE_CHUNKING` | false | 结构化切块实验 |

## 已废弃

| 项 | 替代 |
| --- | --- |
| `ENABLE_EMBED_ON_COMMIT` | **`EMBEDDING_ENABLED`**（`.env`，同时管 commit 写向量与检索） |

非法组合校验：`validate_flag_combination()` / `tests/migration/test_feature_flag_combination_matrix.py`
