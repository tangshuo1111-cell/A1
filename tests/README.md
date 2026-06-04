# Tests Matrix

当前测试套件目标：**稳定回归**——日常改动必须能快速验证默认主链、三 Agent、RAG/Tool 关键路径。

## 物理分层

| 目录 | 中文 | 测什么 | 失败通常意味着 |
| --- | --- | --- | --- |
| `tests/unit/` | 单元测试 | 单函数 / 小模块 | 局部逻辑错误 |
| `tests/integration/` | 集成测试 | 跨模块主链 | API / DB / RAG 链路不通 |
| `tests/smoke/` | 冒烟测试 | 最小主路径 | **系统不能跑** |
| `tests/backend/` | 后端专项 | Agent / gate / chat 主链 | 业务规则回归 |
| `tests/acceptance/` | 验收测试 | 端到端场景 | 用户路径终态不对 |
| `tests/migration/` | 迁移契约 | 架构切换后行为不变 | **默认路径被改坏** |
| `tests/baselines/` | 基线夹具 | baseline 样本完整性 | trace/perf 对照材料损坏 |
| `tests/_support/` | 测试支撑 | bootstrap / helpers | — |
| `tests/fixtures/` | 测试素材 | 样本文件 | — |

## 常用命令

CI 默认门禁（与 GitHub Actions 后端 job 对齐）：

```powershell
python -m pytest -q tests/smoke tests/backend tests/integration tests/unit tests/acceptance tests/migration tests/baselines -m "not real_external" --cov=backend --cov-fail-under=60 --cov-report=xml
```

仅 smoke：

```powershell
python -m pytest -q -m smoke
```

排除真实外部依赖：

```powershell
python -m pytest -q -m "not real_external"
```

## 与验收文档的关系

- **路径验收**：`tests/migration/test_trace_baseline_new.py` ↔ `docs/current/05_目标运行路径与架构验收表.md`
- **产品指标字段**：`tests/backend/application/chat/test_turn_exit_gate.py::test_product_metrics_v1_canonical_fields`
- **评测体系说明**：`docs/pm/评测与验收体系.md`

## 风格约定

- 新测试不再使用 `test_vXXrY_` 命名。
- 新增真实外部依赖测试时，必须带 gate，并归类到 `real_external`。
