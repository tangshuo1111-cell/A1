# 依赖安全审计记录（pip-audit / npm audit）

> 单一事实源：本文件是依赖 CVE 的**人工评估台账**。  
> 治理级别：P2（非主链、非阻断）。

## 1. 治理取舍：后端 pip-audit 半阻断

- CI 中 `pip-audit`（后端）**未评估 CVE 阻断合并**；已评估且不影响主链的 CVE 通过 `--ignore-vuln ID` 豁免（台账 + CI 同批改）。
  - 真源：`.github/workflows/ci.yml`（backend `pip-audit` 步骤）、本文件 §3 台账。
- 前端 `npm audit` 已对齐半阻断：`--audit-level=high` + 官方 registry（`https://registry.npmjs.org`）；镜像 registry 不支持 audit API，不得作为判定依据。
  - 真源：`.github/workflows/ci.yml`（frontend `npm audit` 步骤）、本文件 §3 台账。
- 理由：上游传递依赖的 CVE 常无法即时升级；若直接 hard-fail 且无豁免机制，会把「上游未修」变成「本仓库永久红」= 治理债。
- 红线：**不阻断 ≠ 不评估**。每条豁免 CVE 必须在 §3 表格留痕（评估人 + 结论），杜绝「静默忽略」。

## 2. 如何复跑（与 CI 一致）

```powershell
# 后端（仓库根）
py -3.12 -m pip_audit -r requirements.lock

# 前端（与 CI 一致，须官方 registry）
cd frontend
npm audit --audit-level=high --registry=https://registry.npmjs.org
```

## 3. CVE 人工评估台账

| 评估日期 | 来源 | CVE / GHSA | 包@版本 | 严重度 | 是否影响主链 | 结论 | 依据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-24 | pip-audit | 无（No known vulnerabilities found） | `requirements.lock` 全量 | — | — | 已清 | `py -3.12 -m pip_audit -r requirements.lock` 全量解析，0 CVE |
| 2026-06-30 | npm audit | 无 high/critical（官方 registry） | `frontend/package-lock.json` | — | — | 已清 | 升级 `next`/`eslint-config-next` 至 15.5.19、`vitest` ≥3.2.6 后 `npm audit --audit-level=high --registry=https://registry.npmjs.org` 通过；2 个 moderate（postcss 传递依赖）低于阻断阈值 |

> 结论取值：`已升级` / `暂缓（上游未修）` / `不适用（未触达代码路径）` / `观察`。  
> 「暂缓」与「不适用」必须写明依据（哪条传递依赖约束、或该 API 未被调用）。

## 4. 与其它治理项的边界

- 本记录不改变任何运行时行为，不引入新 Gate，不进入主链事实源。
- 升级依赖属 (a)/(b) 级改动：改 `requirements.lock` 后须复跑默认 CI（含 `check_*` 守卫与 pytest）。
