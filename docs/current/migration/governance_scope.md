# Governance Scope (R20)

## Chat 主链（强约束）

- 入口：`run_chat_turn.py` facade → `turn_orchestrator.py` → `pipeline/*` → `executors/*`
- 守卫：`scripts/report_governance_status.py`（10+ guards，含 patch 深度、compat 消费、pending canonical）
- 行数：`tests/migration/module_size_baseline.json`（50 模块，baseline 只防回涨）

## 非 chat 区域（R20 铺开）

- 看守：`tests/migration/non_chat_module_size_baseline.json`
- 脚本：`scripts/check_non_chat_module_size.py`
- 首批：`storage/store_factory`、session stores、`workers/entry/*`、`tasks/orchestration/*`

## 仍属 draining 的 compat（非零债，有计划）

R19 draining shim 已物理删除；`backend/compat/compat_shim_registry.json` 仅登记 retired 记录，canonical 见 `retrieve_service` / `main_agent.rule_router`。

## 观测（R21）

- JSON：`GET /internal/metrics`
- Prometheus：`GET /internal/metrics/prometheus`
- 面板定义：`docs/current/observability/dashboard_panels.json`
- 告警规则：`docs/current/observability/alert_rules.yaml`
- 健康检查：`scripts/check_observability_health.py`（CI 接入）

## 产品化/运维（仍属可选演进）

- 外部 Grafana/Prometheus 实例接入与 on-call 闭环
- 多实例任务恢复与更强一致性压测
- 前端 E2E 全异常分支浏览器化（pending_kind 主分支已覆盖）
