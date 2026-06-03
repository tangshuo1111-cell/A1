# Critic Rubric (AnswerAgent / Evidence Critic)

> **Authority**: §15 P8 — AnswerAgent = Critic / Verifier / Sign-off  
> **Version**: 1  
> **Producer**: `agents.middle_agent.evidence_checker.build_critic_check` / `build_default_chain_critic_check`

---

## Purpose

`critic_check` 是 MiddleAgent 对材料充分性与证据链的签字结论；AnswerAgent 据此决定 conservative answer、补料 feedback 或放行 final answer。

---

## Required fields

| Field | Type | Meaning |
|---|---|---|
| `critic_check_id` | string | 唯一 ID，`critic_{uuid10}` |
| `unsupported_claims` | list[object] | 无证据支撑的断言 |
| `weak_evidence_claims` | list[object] | 证据片段过少或质量低 |
| `evidence_mismatch` | list[object] | comparison_matrix 与 source_brief 未对齐 |
| `missing_evidence` | list[object] | source_brief 缺 evidence_spans |
| `conflict_without_resolution` | list[object] | 冲突项缺双侧来源 |
| `revision_required` | bool | 任一类 high-severity 缺陷为 true |
| `safe_to_answer` | bool | 有成功来源且无 unsupported_claims |
| `limitations` | list[string] | 必须写入 final answer 的限制说明 |

Optional (multisource): `job_id`, `comparison_id`.

---

## Scoring rules

### `safe_to_answer = true` 当且仅当

1. 至少一个成功 `source_brief`（default chain）或 comparison 链路完整（multisource）
2. `unsupported_claims` 为空
3. `missing_evidence` 不触发 revision（default chain 允许 material_sufficiency=sufficient 时放宽）

### `revision_required = true` 当

- 存在 `unsupported_claims`，或
- 存在 `missing_evidence`（multisource），或
- 存在 `conflict_without_resolution`

### Weak evidence

- `quality == "low"` 或 `len(evidence_spans) == 1` → 记入 `weak_evidence_claims`
- 不单独阻断 `safe_to_answer`，但必须追加 `limitations`

### Autonomy loop (P8)

`application.chat.autonomy_loop.classify_answer_check` 读取：

- `revision_required == true` → 触发补料 / 下一轮
- `safe_to_answer == false` → conservative 或 feedback

---

## Claim object schema (minimum)

```yaml
claim: string
reason: string
severity: enum [high, medium, low]   # unsupported / weak only
suggested_action: enum [remove_from_final_answer, state_limitation_or_request_feedback]
related_source_id: string          # optional
related_chunk_id: string           # optional
```

---

## Negative examples (must fail rubric)

1. `safe_to_answer: true` 且 `unsupported_claims` 非空
2. 缺少 `critic_check_id`
3. `revision_required: true` 但 autonomy loop 未记录 `loop_id` trace

---

## Positive example (default chain)

```json
{
  "critic_check_id": "critic_abc123def4",
  "unsupported_claims": [],
  "weak_evidence_claims": [],
  "evidence_mismatch": [],
  "missing_evidence": [],
  "conflict_without_resolution": [],
  "revision_required": false,
  "safe_to_answer": true,
  "limitations": []
}
```
