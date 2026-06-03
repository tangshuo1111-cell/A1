# LaneDecision Schema

> **Authority**: §15.4.1 of 平台图+三强自治核心架构迁移执行计划.md  
> **Version**: 1  
> **Pydantic model**: `backend/application/ingress/lane_decision_schema.py`

---

## Schema

```yaml
schema: LaneDecision
version: 1
required:
  - request_id
  - lane
  - mode
  - router_source
  - router_confidence
  - escalated_to_main_agent
optional:
  - reason
  - fallback_chain
  - decided_at_ms
fields:
  request_id:
    type: string
    pattern: "^req_[a-zA-Z0-9_]{6,}$"
  lane:
    type: enum
    values: LANE          # see enums.md
  mode:
    type: enum
    values: MODE          # see enums.md
  router_source:
    type: enum
    values: ROUTER_SOURCE # see enums.md
  router_confidence:
    type: float
    range: [0.0, 1.0]
  escalated_to_main_agent:
    type: bool
  reason:
    type: string
    default: ""
  fallback_chain:
    type: list[enum LANE]
    default: []
  decided_at_ms:
    type: int
    default: 0
```

---

## Example (positive)

```yaml
request_id: "req_abc123"
lane: "video"
mode: "fast"
router_source: "rule+light_classifier"
router_confidence: 0.93
escalated_to_main_agent: false
reason: "explicit video url + summarize intent"
fallback_chain: ["general"]
```

## Example (negative — validation MUST reject)

```yaml
request_id: "bad"            # too short, no req_ prefix
lane: "unknown_lane"         # not in LANE enum
mode: "sync"                 # not in MODE enum
router_confidence: 1.5       # out of range
```

---

## Compatibility constraints

- New fields MUST be optional with a default.
- Existing field types MUST NOT change.
- Breaking changes require `version: 2` and a deprecation note.
