# Feature Flag 灰度切换表 (§15.8.2) — 已归档

> **归档说明**：本表是 P6–P9 迁移期的灰度切换计划，迁移已完成。
> 当前 `backend/config/feature_flags.py` 中相关能力 flag 默认 **全部为 ON**，
> 且不再存在 `ENABLE_OLD_UNIFIED_MAIN_CHAIN` kill switch。
> 本文仅作历史灰度方案存档，不代表当前运行事实。

> 原则：**开 1 关 1** — 每开新开关须保留 `ENABLE_OLD_UNIFIED_MAIN_CHAIN` kill switch。

| Flag | 默认 | 建议灰度窗口 | 值班 | 前置条件 | 回滚 |
|---|---|---|---|---|---|
| `ENABLE_INGRESS_ROUTER_V2` | OFF | T+0 10% session | app-oncall | trace 含 lane/mode；3 baseline 通过 | `INGRESS=false` + `OLD_CHAIN=true` |
| `ENABLE_FAST_LANE_VIDEO` | OFF | T+1 20% video 请求 | app-oncall | video_fast_path trace | 关 FAST_LANE_VIDEO |
| `ENABLE_FAST_LANE_DOCUMENT` | OFF | T+1 20% doc 请求 | app-oncall | document_fast_path trace | 关 FAST_LANE_DOCUMENT |
| `ENABLE_FAST_LANE_WEB` | OFF | T+2 20% web 请求 | app-oncall | web_fast_path trace | 关 FAST_LANE_WEB |
| `ENABLE_FAST_LANE_KB` | OFF | T+2 20% kb 请求 | app-oncall | kb_fast_path trace | 关 FAST_LANE_KB |
| `ENABLE_FAST_LANE_GENERAL` | OFF | T+3 10% general | app-oncall | general fast 不越权 | 关 FAST_LANE_GENERAL |
| `ENABLE_THREE_AGENT_AUTONOMY` | ON (P8) | T+0 5% complex | agents-oncall | critic rubric + loop_id trace | 关 THREE_AGENT_AUTONOMY |
| `ENABLE_ASYNC_CONTROL_PLANE_V2` | OFF | T+4 10% 长任务 | workers-oncall | Redis/memory queue 联调通过 | 关 ASYNC_V2 |
| `ENABLE_OLD_UNIFIED_MAIN_CHAIN` | ON | — | — | 始终可回旧链 | 设为 true |

## Commit 规则

- 开关 **OFF → ON** 必须独立 commit（不与功能代码同 commit）
- 每个开关上线前：`tests/migration/test_*` ≥ 3 baseline sample 绿

## 验收命令

```bash
py scripts/check_import_boundaries.py
py -m pytest tests/migration/ tests/baselines/ -q
```
