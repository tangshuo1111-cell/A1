# 指标观测 Runbook（v2.2 定稿）

> **DoD（产品化观测阶段关闭）**：连续 2 个 **REAL** weekly（沙箱 `:8001` + `5433`，`complex N≥30`）北极星2 ≥70% + 回滚演练通过 + pm 文档对齐。  
> **:8000 主链**仅做行为烟测，**不计入 DoD weekly**（避免写 `light_maqa` 主库 metrics）。

## 前置 checklist

- [ ] `backend/config/env.txt` 已配 LLM key（REAL 跑）
- [ ] Docker 沙箱 PG healthy（`metrics_sandbox-postgres-1`，5433）
- [ ] 确认 `:8000` 的 `DATABASE_URL` — 若指向 `light_maqa`，eval **禁止** `--report` 写 metrics
- [ ] 观测期 freeze `git rev`；仅允许 **(a)** 热修（热修后 O1 时钟重置）

## 命令（单一入口）

| 目的 | 命令 | 进 DoD |
|---|---|---|
| 回滚演练 S1 | `pwsh -File scripts/run_metrics_sandbox.ps1 -RollbackProbe -FakeLLM` | 否 |
| 沙箱 REAL O1 | `pwsh -File scripts/run_metrics_sandbox.ps1 -RefineV2` | **是** |
| 管线连通 | `pwsh -File scripts/run_metrics_sandbox.ps1 -FakeLLM -RefineV2` | 否 |
| Shadow 审计 | `... -RefineV2 -ExitShadow -FakeLLM` | 否 |
| 主链烟测 S2 | `:8000` 起 backend → `run_eval_suite.py --suite v1_route_exit_state`（FAKE/REAL 均可，**不写 DoD**） | 否 |

## 账本

每次沙箱样本跑完 append：`_local/reports/metrics/observation_ledger.jsonl`（stdout 有 `LEDGER:` 行）。

字段：`git_rev`, `environment`, `refine_v2`, `north_star2`, `counts_for_dod`.

## 回滚 L1 / L2

| 级别 | 条件 | 动作 |
|---|---|---|
| **L1 告警** | 单点 REAL weekly <65% 或 P95 >2× baseline | 记 ledger，查 LLM/超时 |
| **L2 回滚** | **连续 2 个有效 REAL weekly** <65%，或逻辑码主导失败 | `ENABLE_COMPLEX_REFINE_V2=0` 或 default OFF |

**无效轮**：该轮 complex 中 timeout/execution_error 占比 ≥20% → 不计 DoD、不触发 L2。

**逻辑回退即停**：失败 Top3 为 `upgrade_still_partial` / `material_*` 等逻辑码 → 立即 default OFF，不等第二 weekly。

## O1 / O2

- O1：同 commit **3 轮** REAL（间隔 ≥4h）；快检可看 1 轮 + ledger
- O2：跨 **1 周** L1/L2 观测（日历时间）
