# 真实 regression_all 回归验证报告

> 生成时间：2026-06-16（最新复跑：11:20）  
> 运行环境：真实 LLM（`LIGHT_MAQA_FAKE_LLM=0`），backend `http://127.0.0.1:8000`  
> 说明：本报告为脱敏摘要；原始 JSON/MD 留在 `runtime_data/eval_sandbox/reports/`（不入库）。

---

## 1. 本轮结论

- 已在真实环境下运行 V1 / V2 / V2.5 / V3 及 **regression_all**。
- **最新结果（2026-06-16 修正 V1 allowed_lanes 后复跑）**：**42/42 passed**，四套件均为 **passed**。
- **failed_unknown / case_timeout / backend_unavailable**：均无。
- **suspected_product_issue**：无。先前 2 例 V1 failed_unknown 已归因并修正为 **评测 case 口径问题（A）**，非产品 lane 标注错误。

**regression_all 最新总览**：`runtime_data/eval_sandbox/reports/eval_v4_regression_overview_20260616_112055.json`

### V1 两例 failed_unknown 归因摘要（已处理）

| case_id | 原失败 | 最终归因 | 处理 |
| ------- | ------ | -------- | ---- |
| general_complex_compare | lane=web ∉ allowed | **A. case allowed_lanes 过窄** | 扩展允许 `web`（ingress router_lane）；保留 primary_path / task_status 断言 |
| mixed_evidence_complex | lane=document ∉ allowed | **A. case allowed_lanes 过窄** | 扩展允许 `document`、`web`；保留 primary_path / partial 诚实性断言 |

**归因依据（只读）**：

- 产品出口将 `extra.lane` 设为 ingress `router_lane`（材料/来源信号）；`primary_path` 才是能力路径。
- 两例 `task_status` / `primary_path` / `mode` 均符合场景；extractor 正确读取 `extra.lane`；两次独立报告一致 → 排除 runner bug 与 LLM 偶发漂移。
- 扩展 `allowed_lanes` **未降低** `task_status`、`primary_path`、`must_not_happen` 规则；route_exit_state 类别不触发 web/document 专项 fake-success 放宽。

**未改业务主链**（`backend/application/chat/**`、`agents/**`、`tools/**` 均无改动）。

---

## 2. 运行环境

| 组件 | 状态 |
| --- | --- |
| backend /health | ok（`light_maqa`） |
| PostgreSQL | ok |
| LLM | configured（key present, length=51, masked=`sk****gg`） |
| LIGHT_MAQA_FAKE_LLM | `0` |
| REAL_EXTERNAL_RUN_REGRESSION | 未设置 |

real_external_smoke capability：**7/7 passed**，`product_failure_cases_count=0`（`eval_real_external_smoke_20260616_104454`）。

---

## 3. suite 结果总表（最新）

| suite | passed/total | status | report（脱敏路径） | 说明 |
| ----- | ------------ | ------ | ------------------ | ---- |
| v1_route_exit_state | **10/10** | **passed** | `runtime_data/eval_sandbox/reports/eval_v1_route_exit_state_20260616_111418.json` | V1 allowed_lanes 已对齐 source-aware routing |
| v2_capability_all | 16/16 | passed | `runtime_data/eval_sandbox/reports/eval_v2_capability_all_20260616_111722.json` | |
| v2_5_multiturn_state | 8/8 | passed | `runtime_data/eval_sandbox/reports/eval_v2_5_multiturn_state_20260616_111837.json` | |
| v3_complex_agent | 8/8 | passed | `runtime_data/eval_sandbox/reports/eval_v3_complex_agent_20260616_112055.json` | |
| regression_all（V4 总览） | **42/42** | **全 passed** | `runtime_data/eval_sandbox/reports/eval_v4_regression_overview_20260616_112055.json` | unknown_failures=[] |

---

## 4. failed case 明细

**最新复跑：无 failed case。**

历史 failed_unknown（已修正，仅供审计）：

| suite | case_id | failure_type | 原 failed_assertions | actual 摘要 | 归因 |
| ----- | ------- | ------------ | -------------------- | ----------- | ---- |
| v1 | general_complex_compare | failed_unknown → 已修复 | lane=web | task_status=succeeded；primary_path=agno_basic_v2_kb；mode=complex | case 口径：lane 表 ingress 来源，应允许 web |
| v1 | mixed_evidence_complex | failed_unknown → 已修复 | lane=document | task_status=partial；primary_path=agno_basic_v2_kb_v3_web | case 口径：混合证据应允许 document/web 来源 lane |

---

## 5. 与 real_external_smoke 的关系

- **real_external_smoke capability 7/7 passed** — 外部能力探针与环境就绪性。
- **本报告** — 历史 regression suite（V1–V3）完整 `/chat/agno` 断言。
- 两者独立；V1 case 口径修正属于**评测层**，不代表 capability smoke 结论变化。
- optional regression 失败不等于 capability 失败；本次 regression_all **42/42**。

---

## 6. 后续建议

### 必须修

- 无（regression 全绿）。

### 建议后续归因

- `known_issues.md` 中部分 KI 已标 Fixed 但文档 status 仍为 Deferred — 建议单独轮次同步文档与证据（本轮未改 known_issues.md）。

### 可以暂不处理

- V4 总览 `final_verdict`「已完成」表示报告门禁完成，非产品零缺陷声明。
- v0_smoke.yaml 中同名 case 若仍用旧 allowed_lanes，可在后续单独对齐（本轮仅改 V1）。
