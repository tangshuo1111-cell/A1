# Real External Smoke 脱敏样例报告

> **说明**：本报告为脱敏样例，基于 staging 稳定运行结果整理；不是原始 JSON。  
> 原始报告路径：`runtime_data/eval_sandbox/reports/eval_real_external_smoke_*.json/md`（不入库）。

## Environment Summary

- env_files_loaded: `backend/config/env.txt`（路径已脱敏，不含内容）
- LIGHT_MAQA_FAKE_LLM: `0`
- DATABASE_URL_set: `true`
- REAL_VIDEO_TEST_URL_set: `false`
- REAL_EXTERNAL_RUN_REGRESSION: `0`
- LLM_API_KEY: present=true, length=51, masked=`sk****gg`

## Dependency Preflight

| id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| backend | configured_and_passed | true | false | health_ok |
| postgres | configured_and_passed | true | false | select_ok |
| playwright | configured_and_passed | true | false | playwright_available |
| ffmpeg | configured_and_passed | true | false | ffmpeg_available |
| llm_key | configured_and_passed | true | false | llm_key_present |
| asr_key | not_configured | false | false | missing_asr_key |
| ocr_key | configured_and_passed | true | false | ocr_key_present |

## Capability Cases

| case_id | status | configured | product_failure | reason |
| --- | --- | --- | --- | --- |
| llm_real_minimal | configured_and_passed | true | false | llm_response_ok |
| web_static_real | configured_and_passed | true | false | web_evidence_present |
| document_fixture_real | configured_and_passed | true | false | document_parsed |
| kb_real_roundtrip | configured_and_passed | true | false | kb_roundtrip_ok |
| video_subtitle_probe_real | configured_and_passed | true | false | subtitle_found |
| asr_real_short_audio | not_configured | false | false | missing_asr_key |
| ocr_real_sample | configured_and_failed | true | false | credential_invalid |

## Optional Regression

- enabled: `false`
- reason: `REAL_EXTERNAL_RUN_REGRESSION not set`

## Summary Counts

- configured_cases_count: 6
- passed_configured_cases_count: 5
- not_configured_cases_count: 1
- dependency_missing_cases_count: 0
- external_timeout_cases_count: 0
- skipped_cases_count: 0
- failed_cases_count: 0
- product_failure_cases_count: 0

## Final Verdict

`environment_ready`（exit_code=0；5/6 configured capability 通过；ASR 未配置；OCR 凭证/样本环境问题，非 product_failure）

## Recommendations

- 配置 ASR provider/key 以覆盖 `asr_real_short_audio`。
- OCR 样本无文本时属环境/样本问题；换有效扫描件或检查 OCR 凭证后再测。
- 可选：`REAL_EXTERNAL_RUN_REGRESSION=1` 叠加精简回归（不计入 capability passed count）。
