# Real External 真实验证总结报告

> 生成时间：2026-06-16  
> 套件：`real_external_smoke`（capability 主报告，非 optional regression）

## 1. 本次真实验证结论

- 已真实执行一次 `real_external_smoke` capability 主报告（`py scripts/evaluation/run_eval_suite.py --suite real_external_smoke`）。
- **capability 7/7 passed**
- **final_verdict=environment_ready**
- **exit_code=0**
- **product_failure_cases_count=0**
- 本次未启用 `REAL_EXTERNAL_RUN_REGRESSION`；optional regression 未纳入 capability 主结论。

脱敏样例详见：`docs/evidence/real_external_smoke_sample.md`  
原始 runtime 报告：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_20260616_104454.json`（不入库）

## 2. 真实通过的能力

| 能力 | case_id | reason |
| --- | --- | --- |
| LLM | llm_real_minimal | llm_response_ok |
| Web | web_static_real | web_evidence_present |
| Document | document_fixture_real | document_parsed（2/2 fixture） |
| KB roundtrip | kb_real_roundtrip | kb_roundtrip_ok |
| Video subtitle | video_subtitle_probe_real | subtitle_found |
| ASR | asr_real_short_audio | asr_ok（provider: dashscope） |
| OCR | ocr_real_sample | ocr_ok（stable PNG fixture） |

## 3. 运行环境摘要

| 组件 | 状态 | 说明 |
| --- | --- | --- |
| backend /health | configured_and_passed | health_ok，PostgreSQL 模式 |
| PostgreSQL | configured_and_passed | select_ok |
| LLM | configured_and_passed | llm_key_present，真实最小调用通过 |
| Playwright | configured_and_passed | playwright_available |
| ffmpeg | configured_and_passed | ffmpeg_available |
| ASR provider | configured_and_passed | dashscope，asr_key_present |
| OCR provider | configured_and_passed | ocr_key_present，PNG fixture 识别通过 |
| video fixture | configured_and_passed | 本地字幕探针 subtitle_found |

环境变量摘要（不含 key 内容）：

- `LIGHT_MAQA_FAKE_LLM=0`（真实 LLM）
- `REAL_EXTERNAL_RUN_REGRESSION=0`（未跑 optional regression）
- `DATABASE_URL_set=true`

## 4. optional regression 说明

- optional regression（V1 route exit / V2.5 multiturn / V3 complex agent / V4 overview）是**附加回归**，不属于 capability 主报告。
- 本次正式 capability 主报告**未启用** `REAL_EXTERNAL_RUN_REGRESSION`。
- 若后续启用 optional regression，V1 `failed_unknown` 与 V3 `case_timeout` 需**单独归因**，不得混入 capability 7/7 主结论或 `product_failure_cases_count`。

## 5. 面试可讲结论

本项目已完成从 mock / fake LLM 评测到**真实外部能力 smoke** 的闭环：

- LLM、Web 静态抓取、Document 解析、KB 入库检索 roundtrip、Video 本地字幕、ASR（dashscope）、OCR（稳定 PNG fixture）共 **7 项 capability 真实调用通过**。
- 评测层 `real_external_smoke` 与业务主链（`/chat/agno`）隔离，专用于 staging 环境可复现性验证。
- `final_verdict=environment_ready` + `product_failure_cases_count=0` 表明当前 staging 环境具备完整真实 smoke 验收条件。
