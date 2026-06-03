"""Single-source material sufficiency derivation for Middle bundles."""

from __future__ import annotations

from application.chat.chat_contracts import KbSufficiencyResult, MaterialSufficiencyResult


def evaluate_material_sufficiency(
    *,
    try_rag: bool,
    knowledge_block: str | None,
    web_block: str | None,
    retrieved_chunks_count: int,
    temporary_materials_count: int,
    commit_results_count: int,
    kb_sufficiency: KbSufficiencyResult | None,
    material_insufficient: bool,
    retrieval_trace_info: dict[str, object] | None,
) -> MaterialSufficiencyResult:
    """Derive one authoritative material sufficiency result for the bundle."""
    reasons: list[str] = []
    trace = retrieval_trace_info or {}
    has_non_kb_material = bool((web_block or "").strip()) or temporary_materials_count > 0 or commit_results_count > 0
    has_kb_material = retrieved_chunks_count > 0 or bool((knowledge_block or "").strip())

    if trace.get("failure_reason") == "source_all_missing_source_id":
        reasons.append("history_anchor_missing_source_id")
        return MaterialSufficiencyResult(level="insufficient", adequate=False, reason_codes=tuple(reasons))

    if material_insufficient:
        reasons.append("material_still_empty_after_gather")
        return MaterialSufficiencyResult(level="insufficient", adequate=False, reason_codes=tuple(reasons))

    if kb_sufficiency is not None and not kb_sufficiency.adequate and not has_non_kb_material:
        reasons.extend(list(kb_sufficiency.reason_codes or ()))
        if kb_sufficiency.hits <= 0 or trace.get("no_match"):
            return MaterialSufficiencyResult(level="no_match", adequate=False, reason_codes=tuple(dict.fromkeys(reasons or ["kb_no_match"])))
        if kb_sufficiency.evidence_tier == "weak" or trace.get("low_confidence"):
            return MaterialSufficiencyResult(level="low_confidence", adequate=False, reason_codes=tuple(dict.fromkeys(reasons or ["kb_low_confidence"])))
        return MaterialSufficiencyResult(level="insufficient", adequate=False, reason_codes=tuple(dict.fromkeys(reasons or ["kb_insufficient"])))

    if has_kb_material or has_non_kb_material:
        return MaterialSufficiencyResult(level="sufficient", adequate=True, reason_codes=())

    if try_rag:
        reasons.append("kb_empty_after_gather")
        return MaterialSufficiencyResult(level="insufficient", adequate=False, reason_codes=tuple(reasons))

    return MaterialSufficiencyResult(level="sufficient", adequate=True, reason_codes=())

