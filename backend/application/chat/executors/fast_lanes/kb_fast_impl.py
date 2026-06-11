"""KB lane fast path implementation (Round 1)."""

from __future__ import annotations

from typing import Any

from application.chat.executors.fast_lanes import fast_llm

_KB_COMPLEX_REASON_CODES = frozenset({
    "comparison",
    "cross_material",
    "decision_tradeoff",
    "multi_dimension",
    "multi_analysis",
    "pro_con",
    "solution_design",
})
_KB_COMPLEX_MARKERS = ("对比", "比较", "异同", "优缺点", "路线图", "优先级", "取舍", "分成", "分为", "从", "角度")


def run_kb_fast_path(
    *,
    message: str,
    context_block: str | None,
    clock,
    shared_prep: Any | None = None,
    ingress: Any | None = None,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.chat.pending_kind import PendingKind
    from application.chat.turn_cache import current_turn_cache
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.knowledge.kb_pipeline import (
        fetch_kb_answer_material_from_probe,
        probe_kb_capability,
    )

    budget_clock = clock
    kb_cache = current_turn_cache()
    prep = shared_prep
    if prep is not None and prep.snapshot is not None and prep.material_text:
        chunks = list(prep.snapshot.chunks)
        trace_info = dict(prep.snapshot.trace_info)
        fact = prep.trace_extra.get("capability_fact")
        advice = prep.trace_extra.get("capability_advice")
        material = prep.material_text or ""
        ranked = chunks
        capabilities_called = list(prep.capabilities_called) or [
            "capability.kb.retrieve",
            "capability.kb.shared_snapshot",
        ]
    else:
        fact, advice, chunks, trace_info = probe_kb_capability(
            message,
            clock=budget_clock,
            turn_cache=kb_cache,
        )
        if advice.suggested_mode != "sync_ok" or not chunks:
            ingress = LaneDecision(
                lane="kb",
                mode="fast",
                router_source="rule",
                router_confidence=0.9,
                router_decision_ms=0,
            )
            arbitrate_mode(
                session_pending=PendingKind.NONE,
                ingress=ingress,
                main_plan=None,
                capability_advice=advice,
                clock=budget_clock,
            )
            return None
        material, ranked, capabilities_called, trace_info = fetch_kb_answer_material_from_probe(
            chunks,
            trace_info,
        )
    if _kb_should_prefer_complex(
        message=message,
        ingress=ingress,
        ranked=ranked,
        evidence_tier=(
            prep.snapshot.evidence_tier
            if prep is not None and prep.snapshot is not None
            else str((fact.metadata.get("evidence_tier") if fact else "") or "")
        ),
    ):
        return None
    if not ranked:
        return None
    answer_text = fast_llm.summarize_fast_material(
        lane="kb", message=message, material=material, context_block=context_block
    )
    kb_suff = getattr(prep, "kb_sufficiency", None) if prep is not None else None
    extra: dict[str, Any] = {
        "fast_path": "kb_fast",
        "lane": "kb",
        "fast_lane_name": "kb",
        "mode": "fast",
        "executor_profile": "fast",
        "rag_context_chars": len(material),
        "v15_retrieved_chunks_count": len(ranked),
        "v14_retrieval_trace": trace_info,
        "capabilities_called": capabilities_called,
        "fast_exit_reason": "kb_retrieve_answer",
        "capability_fact": fact,
        "capability_advice": advice,
        "kb_hits": len(ranked),
        "kb_top_score": (
            prep.snapshot.top_score
            if prep is not None and prep.snapshot is not None
            else (fact.metadata.get("top_score") if fact else None)
        ),
        "kb_evidence_tier": (
            prep.snapshot.evidence_tier
            if prep is not None and prep.snapshot is not None
            else (fact.metadata.get("evidence_tier") if fact else None)
        ),
    }
    if kb_suff is not None:
        extra["kb_sufficiency_level"] = kb_suff.level
    if prep is not None:
        extra["shared_retrieval_used"] = True
    return answer_text, extra


def _kb_should_prefer_complex(
    *,
    message: str,
    ingress: Any | None,
    ranked: list[Any],
    evidence_tier: str,
) -> bool:
    if ingress is None:
        return False
    complex_candidate = bool(getattr(ingress, "complex_candidate", False))
    if not complex_candidate:
        return False
    reason_codes = {
        str(code or "").strip()
        for code in list(getattr(ingress, "complex_reason_codes", []) or [])
        if str(code or "").strip()
    }
    text = (message or "").strip()
    strong_shape = bool(reason_codes & _KB_COMPLEX_REASON_CODES) or any(marker in text for marker in _KB_COMPLEX_MARKERS)
    if not strong_shape:
        return False
    chunk_count = len(list(ranked or []))
    if chunk_count < 2:
        return False
    return str(evidence_tier or "") in {"strong", "usable"}
