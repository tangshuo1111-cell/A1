# 评测可复现性说明

本文说明 LightMultiAgentQA 评测体系的三层可复现边界。

## 1. 离线可复现（无需后端、无需 key）

以下命令在 clone 后即可运行，验证评测框架与治理规则：

```powershell
py -m pytest tests/evaluation/test_eval_real_external_smoke.py -q
py -m pytest tests/evaluation -q
```

包含：

- V0~V4 case schema / rule catalog / regression gate 单测
- KI 专属单测（`tests/unit/test_ki_v*.py`）
- `real_external_smoke` guardrail tests（G1~G10）
- fake LLM / fixture 驱动的 capability 契约测试

**证明的是**：评测器逻辑、状态分类、报告结构、治理边界 — **不是**真实外部能力。

## 2. 本地后端可复现（需 PostgreSQL + 后端，可无外部 key）

```powershell
docker compose up -d postgres
$env:PYTHONPATH = "backend"
py scripts/run_dev.py --backend

py scripts/evaluation/run_eval_suite.py --suite regression_all
```

需要：

- `DATABASE_URL`
- 后端监听 `http://127.0.0.1:8000`

可使用 `LIGHT_MAQA_FAKE_LLM=1` 跑通主链回归，但不证明真实 LLM 质量。

## 3. 真实外部能力可复现（手动 staging smoke）

`real_external_smoke` 启动时会自动加载项目既有 env 文件（与 `backend/config/_helpers.py` 候选路径一致）：

1. 仓库根目录 `.env`
2. `backend/config/env.txt`
3. 上级目录 `.env`（最多 3 层）

规则：`load_dotenv(override=False)` —— **当前 PowerShell 已 export 的变量优先**，不会被 env 文件覆盖。报告只记录 key 是否存在、长度、masked 形态，**不写入完整 key**。

```powershell
# 真实 LLM 需在进程中关闭 fake LLM（可覆盖 env.txt 未设置的项）
$env:LIGHT_MAQA_FAKE_LLM = "0"
# 若未使用 env.txt，也可仅在当前会话 export：
# $env:LLM_API_KEY = "<your key>"
py scripts/evaluation/run_eval_suite.py --suite real_external_smoke
```

若 key 已写在 `backend/config/env.txt`（gitignored），通常**无需**再手动 export `LLM_API_KEY`；但若会话里残留 `LIGHT_MAQA_FAKE_LLM=1`，`llm_real_minimal` 仍会 `skipped`（符合 spec）。

可选：

```powershell
$env:REAL_VIDEO_TEST_URL = "https://..."
$env:REAL_EXTERNAL_RUN_REGRESSION = "1"
py scripts/evaluation/run_eval_suite.py --suite real_external_smoke
```

依赖：

| 依赖 | 用途 |
|------|------|
| LLM key | `llm_real_minimal` |
| 网络 | `web_static_real` |
| PostgreSQL | `kb_real_roundtrip` |
| 文档 fixtures | `document_fixture_real`（`.txt`→`parse_txt_document` 等 registry 名） |
| Playwright Chromium | 动态网页能力边界（preflight） |
| ffmpeg | 视频链（preflight） |
| ASR key | `asr_real_short_audio` |
| OCR key / tesseract | `ocr_real_sample` |
| `REAL_VIDEO_TEST_URL` | `video_subtitle_probe_real`（可选） |

原始报告输出到 `runtime_data/eval_sandbox/reports/`（**不入库**）。

脱敏样例见 [`real_external_smoke_sample.md`](real_external_smoke_sample.md)。

## 4. 哪些情况不算产品失败

| 状态 | 含义 |
|------|------|
| `not_configured` | key/URL 未配置 |
| `dependency_missing` | Playwright/ffmpeg/DB 未就绪 |
| `skipped` | 主动跳过（如 `fake_llm_enabled`） |
| `external_timeout` | 外部超时 |
| `external_unavailable` | 网络不可达 |
| `configured_and_failed` + `credential_invalid` | 凭证无效（环境问题） |

## 5. 哪些情况算产品失败（`product_failure=true`）

- 有正常外部响应，但系统假成功（无 evidence 却声称完成）
- DB 可用但 pending/commit/retrieve 不闭环
- 路由/状态误判掩盖真实失败

仅后者可后续人工判断是否进入 `known_issues.md`；**评测层状态不自动写入 KI 台账**。

## 6. 状态隔离

`real_external_smoke` 的 status 枚举**只属于 evaluation report 层**，不出现在 `/chat/agno` 响应或业务 `task_status` 中。

详见 [`real_external_smoke_spec.md`](real_external_smoke_spec.md)。
