# 依赖安全审计记录（pip-audit / npm audit）

> 单一事实源：本文件是依赖 CVE 的**人工评估台账**。  
> 治理级别：P2（非主链、非阻断）。

## 1. 治理取舍：为什么 informational 不阻断

- CI 中 `pip-audit`（后端）与 `npm audit`（前端）均设 `continue-on-error: true`，**只列出、不阻断合并**。
  - 真源：`.github/workflows/ci.yml`（backend `pip-audit` 步骤、frontend `npm audit` 步骤）。
- 理由：上游传递依赖的 CVE 常无法即时升级（受 `agno` / `sentence-transformers` / `playwright` 等约束）；若直接 hard-fail，会把「上游未修」变成「本仓库永久红」= 治理债。
- 红线：**不阻断 ≠ 不评估**。每条 CVE 必须在下方表格留痕（评估人 + 结论），杜绝「静默忽略」。

## 2. 如何复跑（与 CI 一致）

```powershell
# 后端（仓库根）
py -3.12 -m pip_audit -r requirements.lock

# 前端
# cd frontend; npm audit --omit=dev
```

## 3. CVE 人工评估台账

| 评估日期 | 来源 | CVE / GHSA | 包@版本 | 严重度 | 是否影响主链 | 结论 | 依据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-24 | pip-audit | 无（No known vulnerabilities found） | `requirements.lock` 全量 | — | — | 已清 | `py -3.12 -m pip_audit -r requirements.lock` 全量解析，0 CVE |

> 结论取值：`已升级` / `暂缓（上游未修）` / `不适用（未触达代码路径）` / `观察`。  
> 「暂缓」与「不适用」必须写明依据（哪条传递依赖约束、或该 API 未被调用）。

## 4. 与其它治理项的边界

- 本记录不改变任何运行时行为，不引入新 Gate，不进入主链事实源。
- 升级依赖属 (a)/(b) 级改动：改 `requirements.lock` 后须复跑默认 CI（含 `check_*` 守卫与 pytest）。
