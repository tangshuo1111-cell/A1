# Docs

> **历史文档只读**：`docs/history/` 仅供追溯；运行事实与主链口径以代码与 `backend/application/chat/README.md` 为准。

当前 `docs/` 只保留四类内容：

- `docs/current/`：当前仍需要保留的运行事实、环境说明、验收表、契约、基线与迁移台账
- `docs/pm/`：当前项目说明、产品方案、测试矩阵与求职复用材料
- `docs/evidence/`：外部证据包入口说明
- `docs/history/`：已归档的历史文档、产品文档、阶段性方案与旧口径说明

## 当前保留的必要文档

### 运行与事实

- [current/01_运行说明.md](current/01_运行说明.md)
- [current/02_环境变量与数据库.md](current/02_环境变量与数据库.md)
- [current/03_目标运行路径与架构验收表.md](current/03_目标运行路径与架构验收表.md)
- [current/04_默认路由_材料流与质量门控规则.md](current/04_默认路由_材料流与质量门控规则.md)
- [current/openapi.json](current/openapi.json)

### 契约、基线、迁移

- `current/contracts/`
- `current/baselines/`
- `current/migration/`

### 证据入口

- [evidence/README.md](evidence/README.md)

### 当前 PM / 项目说明

- [pm/01_项目卡.md](pm/01_项目卡.md)
- [pm/02_简版PRD.md](pm/02_简版PRD.md)
- [pm/03_用户场景与失败复盘.md](pm/03_用户场景与失败复盘.md)
- [pm/04_产品指标看板.md](pm/04_产品指标看板.md)
- [pm/05_评测与验收体系.md](pm/05_评测与验收体系.md)
- [pm/06_路由与能力测试矩阵.md](pm/06_路由与能力测试矩阵.md)
- [pm/07_AI产品深度方案.md](pm/07_AI产品深度方案.md)
- [pm/08_竞品分析.md](pm/08_竞品分析.md)
- [pm/09_MVP与优先级.md](pm/09_MVP与优先级.md)
- [pm/10_用户可见状态文案.md](pm/10_用户可见状态文案.md)
- [pm/11_协作周报规范.md](pm/11_协作周报规范.md)
- [pm/12_求职展示版项目说明.md](pm/12_求职展示版项目说明.md)
- [pm/13_求职话术与案例包.md](pm/13_求职话术与案例包.md)
- [pm/14_简历最终成稿.md](pm/14_简历最终成稿.md)

## 历史文档去哪里了

已归档到：

- `docs/history/current/`
- `docs/history/pm/`

其中包括：

- 旧的架构说明、目录规则、目标架构冻结说明
- 阶段性 KB 补强材料
- 产品方案、PRD、测试矩阵、竞品分析、求职材料

这些文档不再作为当前项目的默认事实源，但会继续保留，方便后续回看。

## 现在先看哪几份

如果你只是想快速理解当前项目，先看：

1. [current/04_默认路由_材料流与质量门控规则.md](current/04_默认路由_材料流与质量门控规则.md)
2. [current/03_目标运行路径与架构验收表.md](current/03_目标运行路径与架构验收表.md)
3. [current/01_运行说明.md](current/01_运行说明.md)
4. [current/02_环境变量与数据库.md](current/02_环境变量与数据库.md)
5. [pm/02_简版PRD.md](pm/02_简版PRD.md)
6. [pm/07_AI产品深度方案.md](pm/07_AI产品深度方案.md)

## 当前整理原则

- 主项目只保留必要文档
- 容易和代码现实漂移的说明文档，统一移入 `docs/history/`
- 需要长期被脚本、测试或运行说明引用的文件，继续留在 `docs/current/`
