# Tests Matrix

当前测试套件目标：**稳定回归**——日常改动必须能快速验证默认主链、三 Agent、RAG/Tool 关键路径。

## 物理分层

- `tests/unit/`：纯函数 / 模块级单元测试
- `tests/integration/`：跨模块主链集成回归
- `tests/smoke/`：最小主路径与关键防回归 smoke
- `tests/backend/`：偏后端模块级与 API/Agent 回归
- `tests/acceptance/`：业务验收与历史终态断言
- `tests/_support/`：bootstrap / helper / shared builders
- `tests/fixtures/`：样本与测试素材

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

## 风格约定

- 新测试不再使用 `test_vXXrY_` 命名。
- 新增真实外部依赖测试时，必须带 gate，并归类到 `real_external`。
