# Docs

当前文档分四类：

- `docs/current/`：工程事实源（架构、环境、验收表、contracts、baselines）
- `docs/pm/`：产品文档（PRD、指标、场景、评测说明）
- `docs/evidence/`：外部验收证据包入口说明

## 建议阅读顺序（工程）

1. [01_架构与主路径.md](current/01_架构与主路径.md)
2. [02_目录规则.md](current/02_目录规则.md)
3. [03_运行说明.md](current/03_运行说明.md)
4. [17_默认路由_材料流与质量门控规则.md](current/17_默认路由_材料流与质量门控规则.md)
5. [05_目标运行路径与架构验收表.md](current/05_目标运行路径与架构验收表.md)

## 建议阅读顺序（产品 / 转岗）

1. [pm/项目卡.md](pm/项目卡.md)
2. [pm/简版PRD.md](pm/简版PRD.md)
3. [pm/评测与验收体系.md](pm/评测与验收体系.md)
4. [pm/产品指标看板.md](pm/产品指标看板.md)
5. [pm/用户场景与失败复盘.md](pm/用户场景与失败复盘.md)
6. [pm/协作周报规范.md](pm/协作周报规范.md) — 协作方 HTML 周报

## 周报脚本

```powershell
$env:PYTHONPATH = "backend"
py -3.12 scripts/report_product_metrics.py --days 7 --html
```

产物目录：`_local/reports/metrics/`（不提交）。

## 当前保留

- 核心事实文档：`current/01`、`02`、`03`、`04`、`05`、`08`、`17`
- 产品文档：`pm/*`
- 协议与基线：`current/contracts/`、`current/baselines/`、`current/migration/`、`current/openapi.json`
- 证据入口：[evidence/README.md](evidence/README.md)
