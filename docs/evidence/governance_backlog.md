# 治理 Backlog（阻塞项与原因）

> 用途：登记**当前不在本地安全处理范围内**的治理项，写清阻塞原因与解锁条件，避免被误读成"遗漏"或被强行改动而引入不可验证的回退。  
> 原则：能本地安全收口的已在对应轮次做完；本表只放**需真实 LLM 复跑 42/42** 或 **C 级破坏性契约** 的项。

> **本轮决策（2026-06-24）：先不做（defer）。**  
> BK-1~BK-6 的唯一安全解锁路径是**真实 LLM 复跑 42/42 兜底**（C 级再叠加完整 shadow → eval-gate → 契约退役流程）。在拿到该兜底前强改 = 制造**无法验证的 benchmark 回退** = 违反 L5「benchmark 不回退」。因此本轮不动这些代码，仅保留登记。

## 为什么这些不在本轮做

两条硬约束决定了它们必须 backlog：

1. **验证能力限制**：默认/本地环境是 `LIGHT_MAQA_FAKE_LLM=1`，**无法复跑 42/42 工程回归**。任何改动"路由 / 评测裁定 / 状态语义"的项，若没有 42/42 复跑兜底，就可能引入**无法验证的 benchmark 回退** —— 直接违反 L5「benchmark 不回退」。
2. **改动级别限制**：动稳定出口字段 / compat 出口契约属 **C 级破坏性**，需 shadow → eval-gate → 全套流程，不在"修问题、不增治理复杂度"的本轮范围内。

## Backlog 清单

| ID | 项 | 层 | 阻塞类型 | 解锁条件 |
|----|----|----|----------|----------|
| BK-1 | 评测脆弱性 #2：case yaml `must_not_happen` 文案改稳定状态描述 | L12 | 改评测裁定，需复跑 42/42 | staging 真实 LLM 环境可跑 `regression_all` |
| BK-2 | 评测脆弱性 #3：observability summary 与验收结论彻底分栏 | L12/L13 | 同上（改 runner 输出结构有回归风险） | 同上 |
| BK-3 | 语义路由 cutover：`ENABLE_SEMANTIC_ROUTE_CUTOVER=True` | L9 | 改路由行为，需复跑 42/42 + 路由稳定性证据 | shadow 对比数据达标 + staging 复跑 |
| BK-4 | 主链大模块拆分（`turn_orchestrator` 等，`deferred_cleanup_registry` post-R20） | L0/L3 | 动主链协作/状态，需复跑 42/42 | post-R20 节点 + staging 复跑 |
| BK-5 | `complex_web_kb_compare` 摘除"观察项"标签 | L10 | 需连续多次 staging 通过 | staging 连续 N 次稳定通过 |
| BK-6 | compat 出口镜像层（`compat_builder`）退役 | L1/L5 | C 级破坏性（有 API/前端消费方） | 走 shadow → eval-gate → 全套契约退役流程 |
| BK-7 | 回答质量自动门禁 | L10 | LLM 依赖（FAKE 无法有效判定） | 见下方说明 |

### BK-7 说明（重要：不要另造第二套答案裁决）

回答质量裁决**已存在于主链**，不是缺失：

- `backend/services/capabilities/answer_draft.py::run_light_critic` —— 轻量答案/材料检查
- `backend/agents/middle_agent/evidence_checker.py::build_critic_check` / `build_default_chain_critic_check` —— 证据/答案检查
- `backend/application/chat/autonomy_loop.py::classify_answer_check` —— 把 critic 结果归类，驱动二轮补材

问题不是"没有质量判断"，而是**FAKE LLM 下 critic 无法做有意义的质量判定**（占位回答 → 判定无信号），所以默认 CI 只能测"管线连通"而非"答得好不好"。

**禁止的做法**：在 eval 层另写一个"答案结构/措辞启发式"当质量门 —— 那会形成**第二套答案裁决路径**（违反 L5「不再多层重复裁决」），且本质是脆弱的措辞规则（违反 `eval_governance_guardrails.md`）。

**正确解锁**：在 staging 真实 LLM 环境启用既有 critic 链并随 `full-staging --execute` 复跑观测；CI 永远只测管线，不承诺质量绝对值（口径见 README「当前边界」与 `project_validation_summary.md`）。

## 不阻塞、已在本地收口的（参考，不在本表展开）

- benchmark schema 进 CI、legacy 死测试清理、FAKE 指标诚实化、staging 假步骤、证据新鲜度锚点、CVE 评估台账、Windows gbk 测试 flake、评测脆弱性分级（已对齐）、compat import-shim 退役（已完成）、主链冻结基线核对 —— 详见对应 commit 与 `project_validation_summary.md`。

## 维护规则

- 解锁条件满足后，对应项从本表移除，并在 `project_validation_summary.md` 留痕。
- 严禁为"清空 backlog"而在无 42/42 复跑能力时强改 BK-1~BK-4。
