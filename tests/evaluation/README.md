# Evaluation Test Assets

本目录用于存放评测工程资产，不直接承载业务主链代码。

## Suites

| Suite | 入口 | 默认 CI |
|-------|------|---------|
| V0~V4 regression | `py scripts/evaluation/run_eval_suite.py --suite <name>` | 框架单测 ✅；HTTP E2E ❌ |
| `real_external_smoke` | `py scripts/evaluation/run_eval_suite.py --suite real_external_smoke` | guardrail 单测 ✅；真实调用 ❌ |

`real_external_smoke` 是 V4 之后的真实可复现性补强，**不是 V5**。

## 目录说明

- `schemas/`：评测样例与结果 schema
- `cases/`：评测样例集（含 `real_external_smoke.yaml`）
- `fixtures/`：固定测试资产说明
- `runners/`：loader、断言、sandbox、real_external runner

## 离线测试（可进默认 CI）

```powershell
py -m pytest tests/evaluation/test_eval_real_external_smoke.py -q
py -m pytest tests/evaluation -q
```

## 手动 staging smoke

```powershell
py scripts/evaluation/run_eval_suite.py --suite real_external_smoke
```

详见 `docs/evidence/evaluation_reproducibility.md`。

## 当前边界

默认 CI 下的 evaluation 测试：

- 不调用真实 `/chat/agno`（除手动 smoke）
- 不访问外部网络
- 不跑真实 OCR / ASR / Web / KB（除手动 smoke）
- 不接 LLM judge
