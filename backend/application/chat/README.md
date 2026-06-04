# application/chat — 单轮聊天编排层

本目录是 **POST /chat/agno 的主链**，Agent 与 capability 只被消费，不在此目录外做路由/门控决策。

## 模块分层

| 模块 | 职责 |
|------|------|
| `run_chat_turn.py` | 主序：ingress → approval → shared prep → profile 执行 → 响应 |
| `delivery_gate_flow.py` | 薄层：统一 quality_gate 入口 + trace |
| `quality_gate.py` | 规则：交付 / 升级 profile / 二轮判定（不改 lane） |
| `approval_gate_flow.py` | 薄层：用户确认 + **commit 执行闭环** |
| `approval_gate.py` | 规则：approval 判定 |
| `complexity_policy.py` | `complex_candidate` 结构化信号 |
| `shared_material_prep.py` | KB shared retrieval snapshot |
| `material_flow.py` | 材料层 trace（temporary / pending / committed） |
| `complex_path_entry.py` | executor profile 实现入口（multisource round0 + feedback 执行体） |
| `decision_arbitrator.py` | 硬约束 mode 仲裁（session pending、budget） |
| `response_assembly.py` | 复杂路径 `extra` 组装 |
| `trace_writer.py` | collaboration trace 固定 schema |
| `chat_contracts.py` | 跨模块 dataclass / enum |

## 门控分工（勿混）

```
quality_gate   → 能不能交付 / 要不要升级 / 要不要二轮
feedback_gate  → 二轮动作允不允许（policy / tools）
approval_gate  → 用户是否确认（commit / 长 ASR）
decision_arbitrator → session pending / budget 硬约束
```

## 完整主链（标准口径）

> 术语：`lane`（通道）、`mode` / `executor_profile`（执行档位：fast / complex / async）、`complex_candidate`（复杂题候选信号，不强制初始走 complex）。

### 0. 会话快照 session_snapshot（每轮前置）

```
读取 hist / prev_video / pending_video
  → 可选 turn_stitch（异步任务结果回灌会话）
  → 产出 history_snapshot（供后续 Main / Middle / Answer 消费）
```

### 1. 入口 ingress

```
resolve_lane_decision
  → lane（通道：general / kb / web / video / document）
  → mode（初始执行档位，complex_candidate 默认仍可为 fast）
  → complex_candidate + complex_reason_codes（题型复杂度信号）
  → router_* trace
```

### 2. 用户确认 approval_gate（早退分支）

```
evaluate_turn_approval
  ├─ blocked（拦截）→ approval_blocked 响应
  │     场景：无 pending 却要 commit / 长视频未 confirm / 重处理未确认
  │     extra：approval_gate.* + material_*（pending 层）
  │
  ├─ commit_executed（确认保存并执行入库）→ try_execute_commit_turn 早退
  │     场景：有 pending + 用户 commit 意图
  │     extra：approval_gate.executed + material_layer_used=committed
  │
  └─ 继续（通过）→ 进入下一步
```

### 3. 硬约束仲裁 decision_arbitrator

```
_arbitrate_turn_mode
  → effective_mode（最终执行档位，可相对 ingress.mode 升降）
  → session_pending_kind（会话 pending 语义）
  → 典型：session 有未消化 pending / budget 不足 → 拒绝 fast 或改 complex / async
```

### 4. 共享检索 shared_material_prep（KB 在 fast/complex 之前）

```
run_shared_material_prep（lane 命中 KB 范围时）
  → retrieval_snapshot（检索快照：hits / tier / rag_miss）
  → kb_sufficiency（充分度，simple vs complex 门槛不同）
  → knowledge_block / material_text
  → 写入 turn_cache（本轮幂等）
  → complex 升级后默认不再 retrieve；仅 quality_gate.need_more_material 时 supplementary_retrieve
```

### 5. async 退出口（effective_mode == async 时整轮早退）

```
build_async_pending_result
  → 专项重处理入队（video / web / document 后台任务）
  → extra：executor_profile=async + material_*（temporary / session）+ profile_exit_reason
  → 不进入 fast / complex 答问主链
```

### 6. fast 路径（executor_profile = fast）

```
6a. general 特快（weather / canned / direct_llm）
6b. 专项 fast lane（video / document / web / kb / general）
      → 可选 fast_lane_gate：session pending 不满足 → 直接 effective_mode = complex

每条 fast 产出 answer_text 后，统一经 _maybe_return_fast_result：

  ├─ fast 能力建议 demote async → build_async_pending_result（fast→async 退出口）
  │
  └─ delivery_gate（quality_gate 薄编排）
        ├─ pass（通过）→ 返回 fast 响应
        │     extra：quality_gate.pass + material_* + complex_candidate
        │
        └─ upgrade_profile（升级 complex）→ 不返回，fall-through 到 §7
              extra：quality_gate.upgrade_profile + upgrade_to_agent_reason
```

### 7. complex 路径（executor_profile = complex，含 multi_source_compare 无豁免）

```
7.1 Main.pan        → collaboration_plan（协作计划 / job_type / budget_policy）
7.2 Middle.caipan   → material_bundle（取材：KB / web / pending / 视频等）

7.3 Answer 阶段
  ├─ hard_deadline_limited（≤1.2s 剩余）→ 截止短路答，不跑二轮
  │
  └─ _run_complex_delivery_with_gate（统一门控，multisource 与普通 complex 相同）
        │
        ├─ round0 首答
        │     ├─ job_type == multi_source_compare
        │     │     → run_multisource_round0_answer（仅 round0，禁止 Answer 自触发二轮）
        │     └─ 其他
        │           → run_basic_qa（Answer 首轮）
        │
        ├─ delivery_gate（round_index=0）
        │     ├─ pass → 直接交付 round0 答
        │     └─ need_second_round → 进入二轮执行体（仅此触发源，非 AnswerAgent review）
        │
        ├─ [可选] supplementary_retrieve（need_more_material 时补 KB snapshot）
        │
        ├─ run_feedback_round_execution（二轮执行体，非决策体）
        │     → feedback_gate（动作许可：tools / budget / privacy）
        │     → Middle.caipan(round=1) 或 fetch_web 补材
        │     → autonomy_trace 写入
        │
        └─ [可选] round1 再答（final_answer_based_on_round == round_1 时 run_basic_qa）
```

### 8. 收尾（complex / 最终答问）

```
session_update（hist / pending_video / prev_video）
  → output_guard（截断）
  → response_assembly（_build_extra）
  → 合并 trace：
        ingress complex_* / shared_prep_* / complex_delivery_extra（quality_gate.*）
        material_*（material_trace_from_bundle）
        arbitrator_* / budget_* / turn_cache_*
  → 返回 ChatTurnResult
```

### 9. 全路径 extra 合约字段（任意出口必须具备）

| 字段组 | 含义 | 何时出现 |
|--------|------|----------|
| `material_layer_used` | 材料层：temporary / pending / committed | **所有出口** |
| `material_scope` | 材料范围：session / pending / knowledge | **所有出口** |
| `material_source_count` | 材料来源计数 | **所有出口** |
| `complex_candidate` | 是否复杂题候选 | fast / complex 主链 |
| `quality_gate.pass` | 质量门控是否通过 | 经 delivery_gate 的路径 |
| `quality_gate.upgrade_profile` | 是否 fast→complex 升级 | fast 经 gate 未通过且应升级 |
| `quality_gate.need_second_round` | 是否触发二轮 | complex round0 经 gate |
| `quality_gate.need_more_material` | 二轮是否优先补材 | complex 二轮 |
| `quality_gate.reason_codes` | 门控原因码 | 经 delivery_gate |
| `refine_reason_codes` | 二轮 refine 原因（与 gate 对齐） | complex 二轮 |
| `approval_gate.*` | 用户确认门控 | approval 早退 |
| `profile_exit_reason` | 档位切换原因 | fast→async / fast→complex 等 |
| `executor_profile` | 最终执行档位 | 所有出口 |

### 主链一图（ASCII）

```
session_snapshot
    ↓
ingress（lane + mode + complex_candidate）
    ↓
approval_gate ──blocked──→ 返回
    │ commit_executed ──→ 返回
    ↓ 继续
decision_arbitrator（effective_mode）
    ↓
shared_material_prep（KB snapshot）
    ↓
async? ──是──→ 返回（async 退出口）
    ↓ 否
fast lane 尝试 ──→ delivery_gate ──pass──→ 返回
    │                    │
    │                    └──upgrade──┐
    ↓（fall-through / 初判 complex）│
Main → Middle → Answer round0 ←─────┘
                    ↓
              delivery_gate
                    ↓
         need_second_round?
              ↓ 是
    supplementary_retrieve?（可选）
              ↓
    feedback_round_execution（+ feedback_gate）
              ↓
         round1 再答?（可选）
              ↓
         响应组装 + material_* + quality_gate.*
```

## 相关文档

- 原则与阈值：`docs/current/04_默认路由_材料流与质量门控规则.md`
- Ingress：`backend/application/ingress/`
- KB 充分度：`backend/services/capabilities/knowledge/kb_sufficiency.py`

## 合约测试

```powershell
cd 项目代码
$env:PYTHONPATH="backend"
py -m pytest tests/backend/application/chat/ -q
```

| 测试文件 | 覆盖 |
|----------|------|
| `test_quality_gate.py` | 规则阈值 |
| `test_delivery_gate_flow.py` | 薄 orchestrator |
| `test_feedback_round_execution.py` | 二轮执行体须 quality 触发 |
| `test_approval_gate_flow.py` | pending commit / 长视频确认 |
| `test_material_flow.py` | material_layer / scope |
| `test_gate_integration.py` | fast 升级、KB 门槛、trace 字段 |
