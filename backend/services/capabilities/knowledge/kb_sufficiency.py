"""Unified KB evidence sufficiency — simple vs complex thresholds (doc §4)."""

from __future__ import annotations

from application.chat.chat_contracts import (
    EvidenceTier,
    KbSufficiencyResult,
    RetrievalSnapshot,
)

_SIMPLE_MIN_HITS = 1
_COMPLEX_MIN_HITS = 3
_SIMPLE_MIN_SCORE = 0.25
_COMPLEX_MIN_SCORE = 0.6


def evaluate_kb_sufficiency(
    snapshot: RetrievalSnapshot | None,
    *,
    complex_candidate: bool,
) -> KbSufficiencyResult:
    if snapshot is None or snapshot.hits <= 0 or snapshot.rag_miss:
        return KbSufficiencyResult(
            level="insufficient",
            adequate=False,
            reason_codes=("kb_miss",),
            hits=0,
            top_score=0.0,
            evidence_tier="none",
        )

    hits = snapshot.hits
    top_score = snapshot.top_score
    tier = snapshot.evidence_tier
    reasons: list[str] = []

    if complex_candidate:
        strong_multi_hit = hits >= 2 and tier == "strong" and top_score >= 0.7
        if hits < _COMPLEX_MIN_HITS and not strong_multi_hit:
            reasons.append("kb_hits_below_complex")
        if tier != "strong" or top_score < _COMPLEX_MIN_SCORE:
            reasons.append("kb_tier_below_complex")
        if tier == "weak":
            reasons.append("kb_weak_fallback")
        if reasons:
            return KbSufficiencyResult(
                level="insufficient",
                adequate=False,
                reason_codes=tuple(reasons),
                hits=hits,
                top_score=top_score,
                evidence_tier=tier,
            )
        return KbSufficiencyResult(
            level="adequate_complex",
            adequate=True,
            reason_codes=(),
            hits=hits,
            top_score=top_score,
            evidence_tier=tier,
        )

    if hits < _SIMPLE_MIN_HITS:
        reasons.append("kb_hits_below_simple")
    if top_score < _SIMPLE_MIN_SCORE and tier == "weak":
        reasons.append("kb_score_weak")
    if reasons:
        return KbSufficiencyResult(
            level="weak" if hits > 0 else "insufficient",
            adequate=False,
            reason_codes=tuple(reasons),
            hits=hits,
            top_score=top_score,
            evidence_tier=tier,
        )
    return KbSufficiencyResult(
        level="adequate_simple",
        adequate=True,
        reason_codes=(),
        hits=hits,
        top_score=top_score,
        evidence_tier=tier,
    )


def tier_from_score(*, hits: int, top_score: float) -> EvidenceTier:
    if hits <= 0:
        return "none"
    if top_score >= 0.6:
        return "strong"
    if top_score >= _SIMPLE_MIN_SCORE:
        return "usable"
    return "weak"
