# Lane Capability Whitelist

> **Authority（FAST 唯一真源）**: `backend/application/chat/executors/fast_lanes/fast_capability_policy.py` 的 `FAST_CAPABILITY_WHITELIST`。下方分 lane 表中 **fast 列以代码为准**；标 complex 的多为设计/能力名，complex 链不以同一字符串白名单 enforce。  
> **Naming convention**: `capability.<lane>.<verb>`

## FAST_CAPABILITY_WHITELIST（代码逐字，2026-06 口径）

```
video:    subtitle_probe, short_sync_asr, duration_probe
document: probe, parse_quick, parse_pdf_quick, parse_text_or_table, summarize
web:      static_fetch, probe
kb:       probe, retrieve, rerank, grounding
general:  direct_answer, canned_answer, weather_quick, fast_llm
```

跨 lane 例外（`CROSS_LANE_GENERAL_CAPABILITIES`）：`capability.general.fast_llm`、`capability.general.direct_answer`。

> 下方分 lane 明细表为人工说明，如与上方代码块/`fast_capability_policy.py` 冲突，**以代码为准**。

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
`capability.general.fast_llm` 与 `capability.general.direct_answer`，见 `CROSS_LANE_GENERAL_CAPABILITIES`).  
On violation: trace MUST record `cross_lane_violation=true`.  
CI test MUST assert `cross_lane_violation` count is 0.
