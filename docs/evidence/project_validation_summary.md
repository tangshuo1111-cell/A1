# 项目验证总说明（Final）

> 生成口径：2026-06-16  
> 用途：push 前 / 对外讲解 / 评审答辩的**单一索引**  
> 原则：三条验证线**职责分离**；结论**不混报**；原始报告不入库。

---

## 1. 总结论

当前项目已形成 **三层验证体系**：

| 层 | 一句话 | 当前 staging/本地结果 |
| --- | --- | --- |
| **产品指标线** | 6 题代表样本 → PG 指标 → 协作周报（看趋势） | 框架与脚本已落地；样本量小，**不可外推** |
| **工程回归线** | V1–V4 / `regression_all`（看主链 pass/fail） | **42/42 passed** |
| **真实能力线** | `real_external_smoke`（看外部 provider 能否真调通） | **7/7 passed**，`product_failure_cases_count=0` |

补充：

- `tests/evaluation` 单元/守卫测试：**113 passed**（含 eval 框架 guardrail，**不等于** 42 case 全量 E2E 自动在 CI 跑完）。
- 上述 **42/42、7/7** 来自 **本地/staging 真实 LLM 运行**（`LIGHT_MAQA_FAKE_LLM=0`），**不等于**默认 CI 每次 push 自动保证。

**统一入口（只读摘要，默认不跑真实外部能力）**：

```bash
py scripts/evaluation/run_project_validation.py
py scripts/evaluation/run_project_validation.py --profile summary
```

**staging 一键总验收（需 `--execute`，可能产生外部调用与费用）**：

```bash
py scripts/evaluation/run_project_validation.py --profile full-staging
py scripts/evaluation/run_project_validation.py --profile full-staging --execute
```

产物（gitignored）：`runtime_data/eval_sandbox/reports/project_validation_staging_*.json`

---

## 2. 三条验证线

| 验证线 | 目的 | 入口 | 产物 | 当前结果 | 不代表什么 |
| --- | --- | --- | --- | --- | --- |
| **产品指标线** | 产品表现趋势（北极星/护栏/耗时） | `py scripts/run_metrics_sandbox_samples.py --report`<br>`py scripts/report_product_metrics.py --days 7 --html`<br>或 `run_project_validation.py --profile metrics --execute` | PG `turn_product_metrics`<br>`_local/reports/metrics/weekly_*.html` | 6 条代表题 + 周报框架已跑通 | **不是** pass/fail 回归；**不能**代表全量用户；N 小不可外推 |
| **工程回归线** | 主链路由/出口/诚实性/能力链/多轮/复杂协作 | `py scripts/evaluation/run_eval_suite.py --suite regression_all`<br>或 `run_project_validation.py --profile regression` | `runtime_data/eval_sandbox/reports/eval_v4_regression_overview_*.json` | **42/42**（V1 10 + V2 16 + V2.5 8 + V3 8） | **不是** 任意复杂题稳定；**不是** 外部 provider 就绪 |
| **真实能力线** | staging 外部能力探针（LLM/Web/Doc/KB/Video/ASR/OCR） | `py scripts/evaluation/run_eval_suite.py --suite real_external_smoke`<br>或 `run_project_validation.py --profile external` | `runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.json` | **7/7**，`environment_ready` | **不是** 所有网站/视频/OCR 样本；**不是** regression 全绿 |
| **staging 总验收** | 依次跑 regression + real_external，汇总可读摘要 | `py scripts/evaluation/run_project_validation.py --profile full-staging --execute` | `runtime_data/eval_sandbox/reports/project_validation_staging_*.json` | 依赖 staging 环境；**不入库** | **不是** 默认 CI；**不是** 产品指标线 |

**脱敏证据文档（可入库）**：

- 真实能力：`docs/evidence/real_external_validation_report.md`
- 工程回归：`docs/evidence/real_regression_validation_report.md`
- 验收口径：`docs/evidence/real_regression_validation_report.md` §验收口径合法性说明

**规范索引**：

- 产品指标：`docs/pm/04_产品指标看板.md`、`docs/pm/11_协作周报规范.md`
- 工程评测：`docs/pm/05_评测与验收体系.md`

---

## 3. 当前已完成证据

### 3.1 real_external_smoke 7/7

| capability | case | 状态 |
| --- | --- | --- |
| LLM | `llm_real_minimal` | configured_and_passed |
| Web | `web_static_real` | configured_and_passed |
| Document | `document_fixture_real` | configured_and_passed |
| KB roundtrip | `kb_real_roundtrip` | configured_and_passed |
| Video subtitle | `video_subtitle_probe_real` | configured_and_passed |
| ASR | `asr_real_short_audio` | configured_and_passed |
| OCR | `ocr_real_sample` | configured_and_passed |

参考报告（不入库）：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_20260616_104454.json`

### 3.2 regression_all 42/42

| suite | passed/total |
| --- | --- |
| V1 `v1_route_exit_state` | 10/10 |
| V2 `v2_capability_all` | 16/16 |
| V2.5 `v2_5_multiturn_state` | 8/8 |
| V3 `v3_complex_agent` | 8/8 |

参考总览（不入库）：`runtime_data/eval_sandbox/reports/eval_v4_regression_overview_20260616_112055.json`

### 3.3 产品指标线

- **6 条代表题**：`scripts/metrics_sandbox_samples.yaml`
- **指标落库**：PostgreSQL `turn_product_metrics`（常用指标沙箱库，见 `run_metrics_sandbox_samples.py` 注释）
- **协作周报**：`_local/reports/metrics/weekly_*.html`（**不入库**）
- **作用**：产品趋势与协作决策；**不是** pass/fail 回归门禁

---

## 4. CI / workflow 边界

| 工作流 | 触发 | 跑什么 | 与三线关系 |
| --- | --- | --- | --- |
| **`.github/workflows/ci.yml`** | push / PR | gitleaks、ruff、架构 guard、pytest（**fake LLM**，`-m "not real_external"`）、OpenAPI 快照、前端 lint/e2e | **默认 CI**：轻量安全 + 单测/集成；**不跑** `regression_all` E2E、**不跑** `real_external_smoke` |
| **`.github/workflows/real_external.yml`** | **workflow_dispatch**（手动） | `pytest -m real_external`（需 secrets） | **真实外部能力**可选自动化；**不是**每次 merge 默认 |
| **`.github/workflows/nightly_benchmark.yml`** | cron / 手动 | KB benchmark ingest + eval、agent smoke（fake LLM） | 夜间 KB 基准；**不是** 42/42 regression；fixture 位于 `docs/history/current/20–25_KB补强_*.md` |

**必须对外如实表述**：

- ✅ 「项目提供真实验证套件，当前已在 staging 跑通 7/7 + 42/42」
- ❌ 「每次 merge 自动保证 7/7 / 42/42」
- 真实外部能力依赖：**secret / env / provider / staging backend / PG**；应放在 **workflow_dispatch / scheduled / protected staging**，不应塞进默认 CI。
- **无 scheduled regression_all / scheduled real_external_smoke**；复现 42/42 + 7/7 依赖本地/staging 手动执行或 `full-staging --execute`。

### 5.1 Nightly KB Benchmark（2026-06-16 修复说明）

| 项 | 结论 |
| --- | --- |
| 定位 | KB agent eval 夜间基准（`benchmarks/kb_agent_eval`）；**独立于** regression_all / real_external_smoke |
| 历史失败 | `kb-benchmark` ingest 步骤 FileNotFoundError |
| 根因 | ingest 默认读 `docs/current/`，但 benchmark fixture 已归档在 **`docs/history/current/`**（路径未同步） |
| 修复 | `ingest_kb_strengthening_pack.py` 默认改为 `docs/history/current`；**未编造文档、未改业务主链** |
| 与 42/42、7/7 关系 | **无**；Nightly 绿 **不等于** staging 42/42 或 7/7 |

---

## 5. P0 / P1 / P2 状态

### P0（本轮处理）

| 项 | 状态 |
| --- | --- |
| 远程同步（push） | **已解决**（`main` 与 `origin/main` 同步，最新 CI success） |
| 三线验证说明 | 本文件收口 |
| CI 边界说明 | 本文件 §4 + workflow 注释 |
| 统一入口 | `run_project_validation.py`（默认 `summary`） |
| 一键总验收 | **`--profile full-staging`**（dry-run 默认；`--execute` 跑 regression + external） |
| 最强验证 CI 自动化 | **未进默认 CI**（by design）；复现依赖 staging / manual / `full-staging --execute` |
| Nightly KB 红 | **P0.5 已修**（ingest 路径对齐 `docs/history/current`）；push 后待 Nightly 复验 |
| 工作区卫生 | 见 §6；本地 txt / 无关 fixture 二进制 **不得 stage** |

### P1（本轮不修，仅记录）

- 北极星「资料二次调用率」等未完全接线
- 6 题指标样本量小，周报比率不可外推
- `eval_rule_fragility_audit.md` 中措辞/脆弱字段规则仍需治理
- `complex_web_kb_compare` 仍为稳定性观察项
- `lane` / `primary_path` 全库 case 语义需持续对齐
- 指标沙盒 vs `eval_sandbox` 命名易混

### P2（本轮不修）

- 多租户、计费、生产 SLO/告警
- 安全审计（pip-audit 等）阻断策略
- 生产运营与真实用户规模验证
- `docs/history` vs `docs/evidence` 长期单一事实源治理

---

## 6. push 前审查清单

**相对 `origin/main` 无未 push commit 时**，新 commit 应仅涉及：

- `tests/evaluation/**`
- `scripts/evaluation/**`
- `docs/evidence/**`
- `.github/workflows/**`（仅验证边界注释/说明）

**不得包含**：

- `backend/application/chat/**`、`backend/agents/**`、`backend/tools/**`
- `backend/config/env.txt`、`.env`、secret/token
- `runtime_data/eval_sandbox/reports/*`
- `_local/reports/metrics/*`
- 无关 v16 docx/pdf/xlsx 二进制
- 本地临时 txt（如 `docs/pm/主链路.txt`、`项目审查说明.md`、`项目目录树.txt`）

**工作区卫生（当前未提交项）**：

| 文件 | 建议 |
| --- | --- |
| `docs/pm/主链路.txt` | 保留本地或归档；**不要 stage** |
| `项目审查说明.md` | 保留本地或归档；**不要 stage** |
| `项目目录树.txt` | 保留本地或归档；**不要 stage** |
| `tests/fixtures/v16_materials/docx|pdf|xlsx/*`（已修改二进制） | 若与本轮无关：**git restore** 还原；**不要 stage** |
| `backend/config/env.txt` | 已在 `.gitignore`；**绝对不要 stage** |
| `runtime_data/eval_sandbox/reports/*` | gitignored；**不要 stage** |
| `_local/reports/metrics/*` | gitignored；**不要 stage** |

**push 前建议人工确认**：

1. `git log origin/main..HEAD` 与 `git diff origin/main..HEAD --stat` 范围符合上表  
2. staging 证据日期与本文 §3 一致（或更新本文）  
3. 对外话术使用 §7、§8，不混报三线结论  
4. 需要复现 42/42 + 7/7 时，用 `full-staging --execute`，不要声称默认 CI 已覆盖

---

## 7. 对外可讲版本（人话）

这个项目目前 **不是生产 SaaS**，而是一个 **Agentic RAG 工程原型**。它已经形成三层验证：

1. **产品指标周报** — 用 6 条代表题看复杂任务有效完成率等**趋势**；  
2. **工程回归 42/42** — 用 V1–V4 case 看主链路由、出口诚实性、能力链有没有**回归**；  
3. **真实能力 smoke 7/7** — 在 staging 真调 LLM / Web / Document / KB / Video / ASR / OCR，看**环境是否就绪**。

三层结论**互相独立**，不能用一个数字代替另外两个。

---

## 8. 不应夸大的地方

- **42/42** ≠ 任意复杂问题、任意多来源场景都稳定  
- **7/7** ≠ 所有网站 / 视频 / OCR 样本长期稳定  
- **6 题周报** ≠ 全量线上用户表现  
- **默认 CI 绿** ≠ 真实外部能力每次自动 7/7  
- **评测体系完成** ≠ 产品北极星已全部落地  
- **当前阶段** = 可 demo / 可 staging 验证的原型，**不是** 生产 SaaS 1.0  
