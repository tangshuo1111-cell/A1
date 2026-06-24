# 验收证据包（不进主线）

V16「真实验收证据包」正文已从仓库主线移除，以降低 `git clone` 体量。

## 去哪里拿

- GitHub Releases：维护者将原先目录 `V16_真实验收证据包/` 打成 `V16_真实验收证据包.zip` 上传到本仓库 Release（Assets）
- 链接占位：
  `https://github.com/<OWNER>/<REPO>/releases/download/<TAG>/V16_真实验收证据包.zip`

## 评测证据分层

| 位置 | 放什么 | 不放什么 |
| --- | --- | --- |
| `docs/pm/05_评测与验收体系.md` | 阶段结论和摘要 | 不放长篇缺陷细节、不贴原始报告、不写运行日志 |
| `docs/evidence/known_issues.md` | 真实产品缺陷台账 | 不放普通 warning、不放 case 口径问题、不放原始大报告 |
| `runtime_data/eval_sandbox/reports/*` | 原始运行证据 | 不手工改写、不当状态文档、不塞进 PM 文档 |

## 证据新鲜度（自动提醒，避免 silent 漂移）

- 真源标记：以下三份文件首行的 `最新复跑：YYYY-MM-DD` 即新鲜度真值
  - `docs/evidence/project_validation_summary.md`
  - `docs/evidence/real_regression_validation_report.md`
  - `docs/evidence/real_external_validation_report.md`
- 守卫：`scripts/check_evidence_freshness.py`（CI 每次跑，C 级 **warning 不阻断**）；超过 30 天提醒重跑 staging 真实回归 / 外部 smoke
- 重跑后请同步更新上述 `最新复跑` 标记，使 warning 归零

## Evidence 入口

- 三线验证总览（核心）：[`docs/evidence/project_validation_summary.md`](/D:/1/A1_publish/docs/evidence/project_validation_summary.md)
- 真实回归报告：[`docs/evidence/real_regression_validation_report.md`](/D:/1/A1_publish/docs/evidence/real_regression_validation_report.md)
- 真实外部能力报告：[`docs/evidence/real_external_validation_report.md`](/D:/1/A1_publish/docs/evidence/real_external_validation_report.md)
- 轻入口：[`docs/evidence/01_项目评测体系_V1.md`](/D:/1/A1_publish/docs/evidence/01_项目评测体系_V1.md)
- 治理红线：[`docs/evidence/eval_governance_guardrails.md`](/D:/1/A1_publish/docs/evidence/eval_governance_guardrails.md)
- 字段晋升计划：[`docs/evidence/eval_field_promotion_plan.md`](/D:/1/A1_publish/docs/evidence/eval_field_promotion_plan.md)
- 脆弱性盘点：[`docs/evidence/eval_rule_fragility_audit.md`](/D:/1/A1_publish/docs/evidence/eval_rule_fragility_audit.md)
- 治理 backlog（阻塞项与原因）：[`docs/evidence/governance_backlog.md`](/D:/1/A1_publish/docs/evidence/governance_backlog.md)
- 安全审计记录：[`docs/evidence/security_audit_record.md`](/D:/1/A1_publish/docs/evidence/security_audit_record.md)
- known issue 台账：[`docs/evidence/known_issues.md`](/D:/1/A1_publish/docs/evidence/known_issues.md)
- V3 可观测字段勘测：[`docs/evidence/v3_observable_fields_report.md`](/D:/1/A1_publish/docs/evidence/v3_observable_fields_report.md)
- real_external_smoke spec（已实施，已归档）：[`docs/history/evidence/real_external_smoke_spec.md`](/D:/1/A1_publish/docs/history/evidence/real_external_smoke_spec.md)
- 评测可复现性：[`docs/evidence/evaluation_reproducibility.md`](/D:/1/A1_publish/docs/evidence/evaluation_reproducibility.md)
- real_external_smoke 脱敏样例：[`docs/evidence/real_external_smoke_sample.md`](/D:/1/A1_publish/docs/evidence/real_external_smoke_sample.md)
- 当前目录树：[`docs/evidence/project_tree_current.md`](/D:/1/A1_publish/docs/evidence/project_tree_current.md)

## 评测运行产物

评测运行产物统一落在：

- `runtime_data/eval_sandbox/reports/`

当前主要报告命名：

- `eval_v1_route_exit_state_*.json/md`
- `eval_v2_capability_*.json/md`
- `eval_v2_5_multiturn_state_*.json/md`
- `eval_v3_complex_agent_*.json/md`
- `eval_v4_regression_overview_*.json/md`
- `eval_real_external_smoke_*.json/md`（真实外部 smoke，不入库）

当前 V4 总览分类包括：

- `passed`
- `failed_known_issue`
- `failed_unknown`
- `backend_unavailable`
- `case_timeout`
- `execution_error`

其中：

- `failed_known_issue`：真实产品缺陷，且已进入台账
- `backend_unavailable / case_timeout / execution_error`：执行态问题，不等于产品缺陷
