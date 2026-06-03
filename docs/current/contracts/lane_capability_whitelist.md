# Lane Capability Whitelist

> **Authority**: §15.5 of 平台图+三强自治核心架构迁移执行计划.md  
> **Naming convention**: `capability.<lane>.<verb>`  
> Fast and complex share the capability pool; call-count limits differ.

---

## Video Lane

| Capability | fast | complex | fast call limit | Implementation |
|---|---|---|---|---|
| `capability.video.subtitle_probe` | ✅ | ✅ | 1 | `tools/video/extract_*subtitle.py` (probe mode) |
| `capability.video.short_sync_asr` | ✅ | ✅ | 1 | `services/capabilities/video/parallel_asr_service.py` |
| `capability.video.background_asr` | ❌ | ✅ | — | `services/capabilities/video/background_executor.py` |
| `capability.video.duration_probe` | ✅ | ✅ | 1 | `services/capabilities/video/duration_probe.py` |
| `capability.video.summarize` | ✅ | ✅ | 1 (fast) | LLM call |

> Video Fast Path MUST NOT call `background_asr` to avoid implicit async.

---

## Document Lane

| Capability | fast | complex | fast call limit |
|---|---|---|---|
| `capability.document.parse_text_or_table` | ✅ | ✅ | 1 |
| `capability.document.parse_pdf_quick` | ✅ | ✅ | 1 |
| `capability.document.ocr_full` | ❌ | ✅ | — |
| `capability.document.summarize` | ✅ | ✅ | 1 |

> Full OCR in Fast Path MUST escalate to Complex / Async.

---

## Web Lane

| Capability | fast | complex |
|---|---|---|
| `capability.web.static_fetch` | ✅ | ✅ |
| `capability.web.dynamic_render` | ❌ | ✅ |
| `capability.web.heavy_extract` | ❌ | ✅ |
| `capability.web.summarize` | ✅ | ✅ |

---

## KB Lane

| Capability | fast | complex |
|---|---|---|
| `capability.kb.retrieve` | ✅ | ✅ |
| `capability.kb.rerank` | ✅ | ✅ |
| `capability.kb.grounding` | ✅ | ✅ |
| `capability.kb.multi_round_research` | ❌ | ✅ |

---

## General Lane

| Capability | fast | complex |
|---|---|---|
| `capability.general.canned_answer` | ✅ | ❌ |
| `capability.general.weather_quick` | ✅ | ❌ |
| `capability.general.fast_llm` | ✅ | ✅ |
| `capability.general.tool_chain` | ❌ | ✅ |

---

## Cross-lane smuggling prohibition

Fast Path **MUST NOT** call capabilities from other lanes (except
`capability.general.fast_llm`).  
On violation: trace MUST record `cross_lane_violation=true`.  
CI test MUST assert `cross_lane_violation` count is 0.
