# real_external_smoke 最终实施 Spec（定稿 + 不破坏性约束补丁）

> **版本**：v1.1（在 v1.0 基础上增加 guardrail 与不破坏性约束）  
> **定位**：V4 之后的「真实可复现性补强」任务 — **不是 V5，不是新版本体系**  
> **状态**：spec 定稿，待实施（本轮不写实现代码）

---

## 0. 最高原则

`real_external_smoke` **只能是** V4 之后的真实可复现性补强任务。

它**不是**：

- V5
- 新版本体系
- 新业务主链
- 新 Agent 架构
- 新 RAG 架构
- 新业务状态体系
- 新 chat contract
- 新 known issue 体系
- 新默认 CI 门禁
- 第三套验收入口

**唯一入口**：

```text
py scripts/evaluation/run_eval_suite.py --suite real_external_smoke
```

不允许独立主入口。若存在 `run_real_external_smoke.py`，只能是单行 wrapper，内部调用 `run_eval_suite.py`。

---

## 1. 不破坏性约束（强制）

实施与 review 时必须遵守以下 15 条；违反任一条即停止合并。

| # | 约束 |
|---|------|
| 1 | **不允许**修改 `/chat/agno` 请求/响应契约 |
| 2 | **不允许**修改 `ChatTurnResult` / `ChatResponse` / `extra` 的业务字段口径 |
| 3 | **不允许**修改 `task_status` 的业务枚举 |
| 4 | **不允许**修改 `primary_path` / `lane` / `mode` 的业务含义 |
| 5 | **不允许**修改 Answer contract |
| 6 | **不允许**修改 known issue mapping 的既有语义 |
| 7 | **不允许**将 `real_external_smoke` 的 status 写入业务 `extra` |
| 8 | **不允许**将 `not_configured` / `dependency_missing` / `skipped` / `external_timeout` 等评测状态反向污染产品状态 |
| 9 | **不允许**新增第二套 report writer（仅允许在 `eval_result_writer.py` 内扩展函数） |
| 10 | **不允许**新增第二套 suite runner（仅允许 `eval_real_external_runner.py` + `run_eval_suite.py` 分支） |
| 11 | **不允许**新增 V5 或新的版本验收文档 |
| 12 | **不允许**把真实外部测试加入默认 CI |
| 13 | **不允许**提交 `runtime_data/eval_sandbox/reports/*` 原始运行报告 |
| 14 | **不允许**提交 key / cookie / token / secret |
| 15 | **不允许**为测试方便修改 `backend/application/chat`、`backend/agents`、`backend/tools` 的业务逻辑 |

### 1.1 评测层状态隔离（强制）

`real_external_smoke` 的 status 枚举：

- `not_configured`
- `dependency_missing`
- `backend_unavailable`
- `external_timeout`
- `external_unavailable`
- `skipped`
- `configured_and_passed`
- `configured_and_failed`

**只能出现在**：

- `runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.json`（不入库）
- `runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.md`（不入库）
- `docs/evidence/real_external_smoke_sample.md`（脱敏样例，可入库）
- `docs/evidence/evaluation_reproducibility.md`
- `docs/evidence/real_external_smoke_spec.md`（本文档）

**不能出现在**：

- `/chat/agno` response
- `ChatTurnResult.task_status`
- `primary_path` / `lane` / `mode`
- Answer `extra` 业务字段
- `docs/evidence/known_issues.md` 的产品缺陷状态
- V0~V4 suite 的 status 分类（`passed` / `failed_known_issue` / `failed_unknown` 等）

评测层读取产品字段；**不向产品层写入评测字段**。

---

## 2. 文件清单与落点隔离

### 2.1 允许新增/修改（仅评测层 + evidence 文档）

| 文件 | 操作 |
|------|------|
| `tests/evaluation/cases/real_external_smoke.yaml` | 新增 |
| `tests/evaluation/runners/eval_real_external_runner.py` | 新增 |
| `tests/evaluation/schemas/real_external_smoke_case.schema.json` | 新增 |
| `tests/evaluation/test_eval_real_external_smoke.py` | 新增（含 guardrail tests） |
| `scripts/evaluation/run_eval_suite.py` | 修改（增加 suite 分支） |
| `tests/evaluation/runners/eval_result_writer.py` | 修改（扩展 `write_real_external_smoke_report`） |
| `docs/evidence/evaluation_reproducibility.md` | 新增 |
| `docs/evidence/real_external_smoke_sample.md` | 新增（脱敏） |
| `docs/evidence/real_external_smoke_spec.md` | 本文档 |
| `docs/evidence/project_tree_current.md` | 新增 |
| `docs/evidence/README.md` | 修改（索引） |
| `tests/evaluation/README.md` | 修改（边界说明） |

### 2.2 原则上不允许修改

| 路径/文件 | 原因 |
|-----------|------|
| `backend/application/chat/**` | 业务主链 |
| `backend/agents/**` | Agent 业务逻辑 |
| `backend/tools/**` | 工具业务逻辑 |
| `backend/application/chat/response_builders/**` | 响应契约 |
| `backend/application/chat/turn_exit_gate.py` | 出口契约 |
| `backend/application/chat/chat_contracts.py` | 契约定义 |
| `docs/pm/05_评测与验收体系.md` | V0~V4 版本摘要，非本任务范围 |
| `docs/evidence/known_issues.md` | 产品缺陷台账，非环境探测台账 |

若实施中认为**必须**触碰上表文件，须先停止、书面说明原因，**不得直接改**。

### 2.3 明确不新增

- `run_real_external_smoke.py`（除非一行 wrapper）
- V5 文档 / case 集
- 第二套 `eval_*_writer.py`
- 第二套 `run_*_suite.py`（除 `run_eval_suite.py` 内分支）

---

## 3. Suite 结构

### 3.0 启动时 env 加载（评测层）

suite 启动时调用 `load_project_env_files(repo_root, override=False)`，候选路径与 `backend/config/_helpers._candidate_env_files` 对齐：

1. `<repo>/.env`
2. `<repo>/backend/config/env.txt`
3. 上级目录 `.env`（最多 3 层）

**不**在 preflight 阶段 `import config.settings`（避免副作用）；仅 `load_dotenv`。进程内已存在的 `os.environ` 项优先（`override=False`）。

`environment_summary` 可含 `env_files_loaded`、`LLM_API_KEY.present/length/masked`，**禁止**写入完整 key 或 env 文件原文。

### 3.1 `dependency_preflight`（7 项，非 capability case）

| preflight_id | 检测内容 |
|--------------|---------|
| `backend` | `/health` 可连接 |
| `postgres` | `DATABASE_URL` + 最小 `SELECT 1` |
| `playwright` | 包 + Chromium 可执行 |
| `ffmpeg` | `ffmpeg -version` |
| `llm_key` | key 存在性 + `LIGHT_MAQA_FAKE_LLM` 状态 |
| `asr_key` | ASR provider/key 配置存在性（不调用） |
| `ocr_key` | OCR provider/key 配置存在性（不调用） |

### 3.2 `capability_cases`（**7 项**，统一定稿）

| # | case_id | 能力 |
|---|---------|------|
| 1 | `llm_real_minimal` | 真实 LLM 最小问答 |
| 2 | `web_static_real` | 真实静态网页抓取 |
| 3 | `document_fixture_real` | 真实文档解析（`direct_tool`；按扩展名映射 registry 工具名） |

`document_fixture_real` 扩展名 → registry 工具名（只读调用，不改业务）：

| 扩展名 | registry 工具名 |
|--------|----------------|
| `.txt` | `parse_txt_document` |
| `.md` | `parse_md_document` |
| `.docx` | `parse_docx` |
| `.pdf` | `parse_pdf` |
| `.xlsx` / `.xls` | `parse_excel` |

禁止调用不存在的 `parse_text`。`tool_not_found` / `parser_dependency_missing` → `dependency_missing`；至少一个 fixture 解析出文本即 `configured_and_passed`。
| 4 | `kb_real_roundtrip` | KB 写入/检索闭环 |
| 5 | `video_subtitle_probe_real` | 视频字幕 probe |
| 6 | `asr_real_short_audio` | 短音频 ASR |
| 7 | `ocr_real_sample` | 扫描样本 OCR |

> **数量口径**：capability case = **7**；preflight = **7**；二者分属不同报告区块，**不得混为同权重 case**。

### 3.3 `optional_regression`（非默认）

- **不作为** capability case，**不计入** `passed_configured_cases_count`
- 仅当 `REAL_EXTERNAL_RUN_REGRESSION=1` 且 backend preflight 通过时，调用现有 `regression_all`
- 结果写入报告 `optional_regression` 区块

---

## 4. Status / configured / product_failure 规则（修订版）

### 4.1 每条条目字段

```json
{
  "case_id": "web_static_real",
  "status": "configured_and_passed",
  "configured": true,
  "product_failure": false,
  "reason": "",
  "detail": {}
}
```

### 4.2 `status` 枚举

| status | configured | product_failure（默认） |
|--------|------------|-------------------------|
| `not_configured` | false | false |
| `dependency_missing` | false | false |
| `backend_unavailable` | false | false |
| `external_timeout` | true* | false |
| `external_unavailable` | true* | false |
| `skipped` | false | false |
| `configured_and_passed` | true | false |
| `configured_and_failed` | true | **见 §4.3** |

\* 若未实际发起外部调用，则 `configured=false`。

### 4.3 `product_failure=true` 的**唯一**条件

| 场景 | product_failure | status | reason 示例 |
|------|-----------------|--------|-------------|
| key 未配置 | **false** | `not_configured` | `missing_llm_key` |
| key 无效 / 过期 / 认证失败 | **false** | `configured_and_failed` | `credential_invalid` / `external_config_error` |
| provider 超时 | **false** | `external_timeout` | `provider_timeout` |
| 网络不可达 / DNS / 403 | **false** | `external_unavailable` | `network_unreachable` |
| Playwright/ffmpeg/DB 未装 | **false** | `dependency_missing` | `ffmpeg_not_found` |
| 工具未注册 / 解析依赖未安装 | **false** | `dependency_missing` | `tool_not_found` / `dependency_not_installed` |
| `LIGHT_MAQA_FAKE_LLM=1` | **false** | `skipped` | `fake_llm_enabled` |
| **有正常外部响应，但系统假成功**（无 evidence 却声称完成） | **true** | `configured_and_failed` | `fake_success_detected` |
| **DB 可用但 pending/commit/retrieve 不闭环** | **true** | `configured_and_failed` | `kb_lifecycle_broken` |
| 路由/状态误判（吞错、错误 lane 掩盖失败） | **true** | `configured_and_failed` | `routing_honesty_failure` |

> **关键修订**：`credential_invalid` / `external_config_error` 属于**环境/凭证问题**，不是产品逻辑假成功 → `product_failure=false`。

### 4.4 汇总计数

| 字段 | 规则 |
|------|------|
| `passed_configured_cases_count` | **仅** `status=configured_and_passed` |
| `failed_cases_count` | **仅** `product_failure=true` |
| `not_configured_cases_count` | `status=not_configured` |
| `skipped_cases_count` | `status=skipped` |

**禁止**：

- `not_configured` / `dependency_missing` / `skipped` / `external_timeout` / `external_unavailable` / `credential_invalid` → **不计入** `failed_cases_count`
- `skipped` / `not_configured` → **不计入** `passed_configured_cases_count`

### 4.5 `LIGHT_MAQA_FAKE_LLM`

| 条件 | `llm_real_minimal` |
|------|-------------------|
| `LIGHT_MAQA_FAKE_LLM=1` | `skipped`, `reason=fake_llm_enabled`, **禁止** `configured_and_passed` |
| `=0` 且无 key | `not_configured` |
| `=0` 且有 key | 执行直连 LLM 探测（**不走** `/chat/agno`，避免 fake 层） |

---

## 5. Exit Code

| Code | 条件 |
|------|------|
| `0` | runner 正常；`product_failure` 计数 = 0（允许全 `not_configured`） |
| `1` | runner 自身异常 |
| `2` | `backend_unavailable` 且 0 个 capability case 进入 configured 执行 |
| `3` | 存在 `product_failure=true` |
| `4` | `REAL_EXTERNAL_RUN_REGRESSION=1` 且 optional regression 出现 `failed_unknown` |

---

## 6. 报告结构

```json
{
  "suite_name": "real_external_smoke",
  "suite_role": "real_capability_reproducibility",
  "version_note": "V4 post-hardening; not a new eval version",
  "dependency_preflight": [],
  "capability_cases": [],
  "optional_regression": { "enabled": false },
  "summary": {},
  "sanitized_summary": "",
  "recommendations": [],
  "final_verdict": "",
  "exit_code": 0
}
```

- **唯一 writer 扩展点**：`eval_result_writer.write_real_external_smoke_report()`
- 不得新建 `eval_real_external_result_writer.py` 等平行模块

---

## 7. Guardrail Tests（必须纳入 `test_eval_real_external_smoke.py`）

以下测试**全部使用 mock**，不连真实外部，**可进默认 CI**。

### G1. `test_real_external_suite_is_registered_only_in_run_eval_suite`

- `run_eval_suite.py` 的 `--suite` choices 含 `real_external_smoke`
- 仓库内不存在第二套独立 argparse 主入口（扫描 `scripts/evaluation/*.py` 的 `if __name__` + argparse，除 `run_eval_suite.py` 外不得有 `real_external_smoke` 独立 suite 入口）
- 若存在 wrapper，其源码仅调用 `run_eval_suite` 或等价 subprocess

### G2. `test_real_external_status_does_not_enter_product_contract`

- 构造 mock report，断言 status 字符串集合与 `task_status` 业务枚举无交集
- 断言评测 status 不会出现在模拟的 `/chat/agno` extra 键名列表中
- 断言不会修改 `primary_path` / `lane` / `mode` 合法值集合

### G3. `test_real_external_does_not_modify_chat_contract`

- 对比实施前后 `docs/current/openapi.json` 中 `/chat/agno` schema hash（或静态断言：runner 源码无 `ChatTurnResult` 字段写入/新增枚举）
- runner 源码 grep：不得含 `task_status = "not_configured"` 等产品字段赋值

### G4. `test_real_external_does_not_change_known_issue_mapping`

- 导入 `render_eval_overview.KNOWN_ISSUE_CASE_MAP`，断言 key 集合与基线一致（或快照文件）
- 断言 `classify_suite_result` 对 `real_external_smoke` 报告**不**走 known_issue 匹配逻辑（该 suite 无 KI 映射）
- `not_configured` / `dependency_missing` 不得出现在 known_issues 模板字段中

### G5. `test_real_external_uses_eval_writer_extension_not_second_writer`

- `tests/evaluation/runners/` 下不存在 `*real_external*writer*.py`（除 result_writer 内函数）
- `write_real_external_smoke_report` 定义在 `eval_result_writer.py` 内
- 报告 JSON 含 `suite_role=real_capability_reproducibility`，与 V4 overview 的 `version_name` 字段区分

### G6. `test_real_external_not_in_default_ci`

- 读取 `.github/workflows/ci.yml`，断言 pytest 命令**不包含** `real_external_smoke` suite 调用
- 断言 pytest 命令含 `-m "not real_external"` 或等价排除
- `test_eval_real_external_smoke.py` 自身**无** `@pytest.mark.real_external` 标记（或标记仅用于文档，默认 CI 仍收集）

### G7. `test_real_external_report_sanitizer_blocks_secrets`

- 向 sanitizer 喂入含 `sk-xxx`、`Bearer xxx`、`cookie=`、绝对路径 `C:\Users\` 的字符串
- 断言输出不含上述模式
- 断言不含完整 raw provider response body（仅允许长度/状态摘要）

### G8. `test_real_external_not_configured_is_not_passed_or_failed`

- 对 synthetic case results 跑 summary 聚合函数
- `not_configured` → `passed_configured_cases_count` 不增加，`failed_cases_count` 不增加
- `skipped` → 同上
- `dependency_missing` → `product_failure` 计数不增加
- `configured_and_failed` + `reason=credential_invalid` → `product_failure=false`

### G9. `test_real_external_optional_regression_is_not_default_case`

- 默认 env（无 `REAL_EXTERNAL_RUN_REGRESSION`）→ `optional_regression.enabled=false`
- `capability_cases` 列表不含 `regression_all` case_id
- optional regression 结果不计入 `passed_configured_cases_count`

### G10. `test_real_external_product_failure_only_on_honesty_violations`（补充）

- `fake_success_detected` → `product_failure=true`
- `credential_invalid` → `product_failure=false`
- `external_timeout` → `product_failure=false`

---

## 8. CI 与手动运行边界

| 类型 | 默认 CI | 手动/staging |
|------|---------|--------------|
| `test_eval_real_external_smoke.py`（guardrail + runner mock） | ✅ | — |
| `py -m pytest tests/evaluation -q` | ✅ | — |
| `run_eval_suite.py --suite real_external_smoke` | ❌ | ✅ |
| `REAL_EXTERNAL_RUN_REGRESSION=1` | ❌ | ✅ |
| `.github/workflows/real_external.yml` 挂接 smoke | ❌（本轮不改） | 后续可选 `workflow_dispatch` |

---

## 9. 不入库清单

- `runtime_data/eval_sandbox/reports/eval_real_external_smoke_*`
- key / cookie / token / secret
- 原始 provider 响应全文
- 用户本机绝对路径（sample 须脱敏）

**可入库**：`real_external_smoke_sample.md`（脱敏）、`evaluation_reproducibility.md`、本 spec、`project_tree_current.md`

---

## 10. 实施顺序（不变，P0 起）

1. P0：本文档定稿 ✅
2. P1：schema + status 聚合 + writer 扩展骨架
3. P2：preflight runner
4. P3：`run_eval_suite.py` 分支 + **guardrail tests 全绿**
5. P4~P7：capability cases 分批
6. P8：文档 + 脱敏 sample + 目录树
7. P9：本地真实跑一轮（报告不入库）

---

## 11. 架构不破坏性说明（审查用）

### 11.1 为何不破坏 `/chat/agno` 主链契约

- runner **只消费**现有 `/chat/agno` 与工具层返回值，**不写入**新字段
- 不修改 `chat_agno.py`、response builders、exit gate
- LLM 探测走**直连 provider**路径，与 chat 契约无关
- 所有评测 status 止于 evaluation report 文件

### 11.2 为何不形成第二套评测体系

- 仍走 `run_eval_suite.py` 单一入口
- 仍用 `eval_result_writer.py` 单文件扩展
- 不新增 V5 文档、不修改 V0~V4 case YAML
- `suite_name=real_external_smoke` 与 `regression_all` 平级，是 V4 体系下的**补充 suite**，不是新版本

### 11.3 为何不影响 V0~V4 `regression_all`

- `regression_all` 逻辑**零修改**，仅 optional 子进程调用
- 默认不触发（`REAL_EXTERNAL_RUN_REGRESSION` 未设置）
- optional 结果**隔离**在 `optional_regression` 区块，不混入 V4 overview 的 `suite_results` 除非显式合并（本 spec **禁止**自动合并进 V4 overview）

---

## 12. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-15 | 初版 spec |
| v1.1 | 2026-06-15 | 增加 15 条不破坏性约束、状态隔离、guardrail tests、capability 统一为 7、修订 product_failure（credential_invalid 不算产品失败） |
