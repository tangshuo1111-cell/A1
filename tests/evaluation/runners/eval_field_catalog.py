from __future__ import annotations

from dataclasses import dataclass

STABLE_CONTRACT_FIELDS: tuple[str, ...] = (
    "task_status",
    "primary_path",
    "lane",
    "mode",
    "pending_kind",
)


STABLE_RESULT_FIELDS: tuple[str, ...] = (
    "answer",
    "failure_reason_code",
    "commit_status",
    "kb_hit_count",
    "kb_hits",
    "background_task_id",
)


FRAGILE_FIELD_PREFIXES: tuple[str, ...] = (
    "extra.",
    "v6_",
    "v7_",
    "v8_",
    "v10_",
    "v11_",
    "v12_",
    "v13_",
    "v14_",
    "v15_",
    "v16_",
    "trace",
)


FRAGILE_FIELD_NAMES: tuple[str, ...] = (
    "routing_explain",
    "retrieved_chunks",
    "source_briefs",
    "comparison_matrix",
    "feedback_gate_result",
    "temporary_materials",
    "quality_gate.reason_codes",
)


CONTEXTUAL_STABLE_FIELDS: tuple[str, ...] = (
    "quality_gate",
    "material_sufficiency",
    "insufficient_evidence",
    "web_primary_source",
    "web_evidence_chars",
    "transcript_source",
    "text_source",
)


@dataclass(frozen=True)
class FieldClassification:
    field_name: str
    tier: str


def classify_field(field_name: str) -> FieldClassification:
    name = str(field_name).strip()
    if name in STABLE_CONTRACT_FIELDS:
        return FieldClassification(field_name=name, tier="stable_contract")
    if name in STABLE_RESULT_FIELDS:
        return FieldClassification(field_name=name, tier="stable_result")
    if name in CONTEXTUAL_STABLE_FIELDS:
        return FieldClassification(field_name=name, tier="contextual")
    if name in FRAGILE_FIELD_NAMES or name.startswith(FRAGILE_FIELD_PREFIXES):
        return FieldClassification(field_name=name, tier="fragile_observability")
    return FieldClassification(field_name=name, tier="contextual")
