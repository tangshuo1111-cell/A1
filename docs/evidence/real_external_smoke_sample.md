# Real External Smoke 脱敏样例报告

> **说明**：本报告为脱敏样例，基于 2026-06-15 本地一次真实运行结果整理；不是原始 JSON。  
> 原始报告路径：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.json/md`（不入库）。

## Environment Summary

- LIGHT_MAQA_FAKE_LLM: `0`
- DATABASE_URL_set: `false`
- REAL_VIDEO_TEST_URL_set: `false`
- REAL_EXTERNAL_RUN_REGRESSION: `0`

## Dependency Preflight

| id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| backend | backend_unavailable | false | false | backend_unreachable |
| postgres | not_configured | false | false | postgres_not_configured |
| playwright | configured_and_passed | true | false | playwright_available |
| ffmpeg | configured_and_passed | true | false | ffmpeg_available |
| llm_key | not_configured | false | false | missing_llm_key |
| asr_key | not_configured | false | false | missing_asr_key |
| ocr_key | not_configured | false | false | missing_ocr_key |

## Capability Cases

| case_id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| llm_real_minimal | not_configured | false | false | missing_llm_key |
| web_static_real | backend_unavailable | false | false | backend_unreachable |
| document_fixture_real | dependency_missing | false | false | tool_not_found |
| kb_real_roundtrip | backend_unavailable | false | false | backend_unreachable |
| video_subtitle_probe_real | backend_unavailable | false | false | backend_unreachable |
| asr_real_short_audio | not_configured | false | false | missing_asr_key |
| ocr_real_sample | not_configured | false | false | missing_ocr_key |

## Optional Regression

- enabled: `false`
- reason: `REAL_EXTERNAL_RUN_REGRESSION not set`

## Summary Counts

- configured_cases_count: 0
- passed_configured_cases_count: 0
- not_configured_cases_count: 3
- dependency_missing_cases_count: 1
- external_timeout_cases_count: 0
- skipped_cases_count: 0
- failed_cases_count: 0
- product_failure_cases_count: 0

## Final Verdict

`environment_not_ready`（exit_code=2；后端未启动、无 configured case；document 工具未注册记为 dependency_missing）

## Recommendations

- 启动后端（`py scripts/run_dev.py --backend`）后重跑 smoke，以验证 web/kb/video 链路。
- 配置 `DATABASE_URL` 以启用 postgres 预检与 KB 闭环。
- 配置 `LLM_API_KEY` / ASR / OCR / `REAL_VIDEO_TEST_URL` 以覆盖其余 capability。
