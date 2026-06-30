# Contributing

## 真源索引（不在此重复规则）

- 架构与 Agent 协作：`AGENTS.md`
- 改动分级 (a)/(b)/(c)：`AGENTS.md` → 统一治理主轴
- 本地启动：`docs/current/01_运行说明.md`
- 环境变量：`docs/current/02_环境变量与数据库.md`
- 评测/验收红线：`docs/evidence/eval_governance_guardrails.md`
- 治理守卫范围：`docs/current/migration/governance_scope.md`

## 分支命名

`feat/` · `fix/` · `docs/` · `chore/` · `test/`

## Commit 风格（对齐现有 git log）

`feat(scope): …` · `fix(scope): …` · `docs(scope): …` · `test: …`

## PR 自检

- [ ] `py -3.12 -m ruff check .` 通过
- [ ] `py -3.12 -m mypy` 通过
- [ ] 相关 `scripts/check_*.py` 守卫通过
- [ ] `pytest -m "not real_external"` 通过
- [ ] 改动若触及 watched 模块，已同步 `tests/migration/*_baseline.json`

## CHANGELOG 维护规则（硬约束）

仅在 version bump 时更新 `CHANGELOG.md`；日常 commit 不写。历史变更以 `git log` 为准。
