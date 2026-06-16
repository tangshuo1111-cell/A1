# Real External Smoke 脱敏样例报告

> **说明**：本报告为脱敏样例，基于 2026-06-16 正式 capability 主报告整理；不是原始 JSON。  
> 原始报告路径：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.json/md`（不入库）。  
> **optional regression 未纳入本次 capability 主报告结论。**

## Environment Summary

- env_files_loaded: `backend/config/env.txt`（路径已脱敏，不含内容）
- LIGHT_MAQA_FAKE_LLM: `0`
- DATABASE_URL_set: `true`
- REAL_VIDEO_TEST_URL_set: `false`
- REAL_EXTERNAL_RUN_REGRESSION: `0`（未启用 optional regression）
- LLM_API_KEY: present=true, length=51, masked=`sk****gg`

## Dependency Preflight

| id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| backend | configured_and_passed | true | false | health_ok |
| postgres | configured_and_passed | true | false | select_ok |
| playwright | configured_and_passed | true | false | playwright_available |
| ffmpeg | configured_and_passed | true | false | ffmpeg_available |
| llm_key | configured_and_passed | true | false | llm_key_present |
| asr_key | configured_and_passed | true | false | asr_key_present |
| ocr_key | configured_and_passed | true | false | ocr_key_present |

## Capability Cases

| case_id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| llm_real_minimal | configured_and_passed | true | false | llm_response_ok |
| web_static_real | configured_and_passed | true | false | web_evidence_present |
| document_fixture_real | configured_and_passed | true | false | document_parsed |
| kb_real_roundtrip | configured_and_passed | true | false | kb_roundtrip_ok |
| video_subtitle_probe_real | configured_and_passed | true | false | subtitle_found |
| asr_real_short_audio | configured_and_passed | true | false | asr_ok |
| ocr_real_sample | configured_and_passed | true | false | ocr_ok |

**capability 7/7 passed**

## Optional Regression

- enabled: `false`
- reason: `REAL_EXTERNAL_RUN_REGRESSION not set`
- note: optional regression 是附加回归，不属于 capability 主报告；本次正式 capability 主报告未启用。

## Summary Counts

- configured_cases_count: 7
- passed_configured_cases_count: 7
- not_configured_cases_count: 0
- dependency_missing_cases_count: 0
- external_timeout_cases_count: 0
- skipped_cases_count: 0
- failed_cases_count: 0
- **product_failure_cases_count: 0**

## Final Verdict

`environment_ready`（exit_code=0；capability 7/7 passed；product_failure_cases_count=0）

## Recommendations

- Environment smoke completed; review configured_and_passed cases for staging evidence.
- 若需叠加 V1/V2.5/V3/V4 optional regression，请单独设置 `REAL_EXTERNAL_RUN_REGRESSION=1` 并单独归因（如 V1 unknown / V3 timeout），不计入 capability 主报告。
