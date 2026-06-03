from __future__ import annotations

from pathlib import Path

from agents.middle_agent.evidence_checker import (
    build_critic_check,
    build_default_chain_critic_check,
)

RUBRIC_PATH = Path("docs/current/contracts/critic_rubric.md")
REQUIRED_FIELDS = {
    "critic_check_id",
    "unsupported_claims",
    "weak_evidence_claims",
    "evidence_mismatch",
    "missing_evidence",
    "conflict_without_resolution",
    "revision_required",
    "safe_to_answer",
    "limitations",
}


def test_critic_rubric_document_exists_and_lists_required_fields() -> None:
    text = RUBRIC_PATH.read_text(encoding="utf-8")
    assert "safe_to_answer" in text
    assert "revision_required" in text
    for field in REQUIRED_FIELDS:
        assert field in text


def test_build_critic_check_satisfies_rubric_contract() -> None:
    briefs = [
        {
            "source_brief_id": "sb_1",
            "source_id": "src_a",
            "title": "A",
            "key_points": ["point a"],
            "quality": "high",
            "evidence_spans": [{"chunk_id": "c1", "text": "evidence"}],
        },
        {
            "source_brief_id": "sb_2",
            "source_id": "src_b",
            "title": "B",
            "key_points": ["point b"],
            "quality": "high",
            "evidence_spans": [{"chunk_id": "c2", "text": "evidence"}],
        },
    ]
    matrix = {
        "comparison_id": "cmp_1",
        "summary": "compare",
        "evidence_links": [
            {"source_brief_id": "sb_1", "claim": "point a"},
            {"source_brief_id": "sb_2", "claim": "point b"},
        ],
        "conflicts": [],
    }
    critic = build_critic_check({"job_id": "job_1"}, matrix, briefs)
    assert set(critic.keys()) >= REQUIRED_FIELDS
    assert critic["critic_check_id"].startswith("critic_")
    assert critic["safe_to_answer"] is True
    assert critic["revision_required"] is False
    assert critic["unsupported_claims"] == []


def test_build_default_chain_critic_check_flags_revision_when_unsupported() -> None:
    critic = build_default_chain_critic_check(
        material_sufficiency="insufficient",
        evidence_envelopes=[],
        failures=[{"reason": "kb_miss"}],
    )
    assert set(critic.keys()) >= REQUIRED_FIELDS
    assert critic["safe_to_answer"] is False
    assert critic["revision_required"] is True
    assert critic["limitations"]
