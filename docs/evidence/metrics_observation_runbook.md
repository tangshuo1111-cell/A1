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

字段：`git_rev`, `environment`, `refine_v2`, `north_star2`, `north_star2_source`, `counts_for_dod`.

`north_star2` 真源 = `product_metrics.complex_effective_complete_rate`（`north_star2_source=product_metrics`）；`yaml_diagnostic` 仅作样本层快检，**不计 DoD**。

## 回滚 L1 / L2

| 级别 | 条件 | 动作 |
|---|---|---|
| **L1 告警** | 单点 REAL weekly <65% 或 P95 >2× baseline | 记 ledger，查 LLM/超时 |
| **L2 回滚** | **连续 2 个有效 REAL weekly** <65%，或逻辑码主导失败 | `ENABLE_COMPLEX_REFINE_V2=0` 或 default OFF |

**无效轮**：该轮 complex 中 timeout/execution_error 占比 ≥20% → 不计 DoD、不触发 L2。

**逻辑回退即停**：失败 Top3 为 `upgrade_still_partial` / `material_*` 等逻辑码 → 立即 default OFF，不等第二 weekly。

## O1 / O2

- **O1**：同 commit **3 轮** REAL（间隔 ≥4h）；热修后观测时钟重置；快检可看 1 轮 + ledger
- **O2**：跨 **1 周** L1/L2 观测（日历时间，非单次脚本可完成）

### O2 观测期（已启动）

| 项 | 值 |
|---|---|
| 起始日 | **2026-06-29** |
| 计划结束 | 2026-07-06（满 7 日历日） |
| L1 baseline（`44f494d`，N=30 REAL） | 北极星2 **86.7%**；`complex_partial=1`（真 insufficiency） |
| 触发 L1 | 单点 REAL weekly <65% 或 complex P95 延迟 >2× baseline |
| 触发 L2 | 连续 2 个有效 REAL weekly <65%，或逻辑码主导失败 → default OFF |

O2 关单条件：观测期内无 L2 触发，且至少 1 个 REAL weekly ≥70% 与 O1 第二 weekly 同 commit 对齐。

## M1 / A2 / C2

- **M1**：`scripts/metrics_sandbox_samples.yaml` complex **40** 条（总 56）；结构约束：insufficiency≥2、async≥2、reuse 四题不变；REAL 复跑 `-RefineV2` 出 N≥40 weekly。
- **A2**：沙箱 async 轮询默认 **240s**（`SANDBOX_ASYNC_POLL_TIMEOUT_SEC`）；不改北极星分母；async 终态 backlog 见 `KI-METRICS-005`。
- **C2**：`staging_full_validation.yml` 周一 02:00 UTC cron + `workflow_dispatch` 跑 **full-staging REAL LLM**；metrics 沙箱线 **刻意不在 CI 写库**（需隔离 PG），本地 `run_metrics_sandbox.ps1` 为 DoD 真源。
