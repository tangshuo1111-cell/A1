"""Unit tests for RefineKind contract and metrics diagnostic helpers."""

from __future__ import annotations

import pytest

from application.chat.refine_kind import (
    build_complex_failure_breakdown,
    classify_partial_bucket,
    enrich_metrics_diagnostic_row,
    narrow_kb_insufficient_reasons,
    resolve_refine_kind,
    would_answer_only_refine_apply,
)
from config.feature_flags import FEATURE_FLAGS


@pytest.fixture(autouse=True)
def _restore_flags():
    saved = dict(FEATURE_FLAGS)
    yield
    FEATURE_FLAGS.clear()
    FEATURE_FLAGS.update(saved)


def test_narrow_kb_insufficient_when_flag_off():
    reasons = ["kb_insufficient", "answer_too_shallow"]
    assert narrow_kb_insufficient_reasons(
        reasons, lane="general", use_knowledge=False, retrieved_chunks_count=0
    ) == reasons


def test_narrow_kb_insufficient_general_lane():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    out = narrow_kb_insufficient_reasons(
        ["kb_insufficient", "answer_too_shallow"],
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=0,
    )
    assert out == ["answer_too_shallow"]


def test_would_answer_refine_shadow_without_flag():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = False
    assert would_answer_only_refine_apply(
        reason_codes=("answer_too_shallow",),
        need_second_round=True,
        need_more_material=False,
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="短答",
        live=False,
    )


def test_would_answer_refine_live_requires_flag():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = False
    assert not would_answer_only_refine_apply(
        reason_codes=("answer_too_shallow",),
        need_second_round=True,
        need_more_material=False,
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="短答",
        live=True,
    )
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    assert would_answer_only_refine_apply(
        reason_codes=("answer_too_shallow",),
        need_second_round=True,
        need_more_material=False,
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="短答",
        live=True,
    )


def test_material_codes_block_answer_only():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    assert resolve_refine_kind(
        need_second_round=True,
        need_more_material=False,
        reason_codes=("kb_insufficient", "answer_too_shallow"),
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="x",
    ) == "material"


def test_integrity_codes_block_answer_only():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    assert resolve_refine_kind(
        need_second_round=True,
        need_more_material=False,
        reason_codes=("answer_truncated", "answer_too_shallow"),
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="x",
    ) == "none"


def test_resolve_answer_only_depth_codes():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    assert resolve_refine_kind(
        need_second_round=True,
        need_more_material=False,
        reason_codes=("complex_answer_not_deep_enough", "case_analysis_missing"),
        insufficient_evidence=False,
        pending_kind=None,
        answer_text="分析不够深",
    ) == "answer_only"


def test_classify_partial_bucket_answer_only_gap():
    row = {
        "task_status": "partial",
        "failure_reason_code": "upgrade_still_partial",
        "quality_gate_reason_codes": ["complex_answer_not_deep_enough"],
        "answer_summary": "浅答",
        "is_complex_task": True,
    }
    assert classify_partial_bucket(row) == "answer_only_gap"


def test_enrich_metrics_diagnostic_row():
    row = {"id": "c1", "task_status": "partial", "is_complex_task": True}
    extra = {
        "quality_gate.reason_codes": ["complex_answer_not_deep_enough"],
        "quality_gate.need_second_round": True,
        "quality_gate.need_more_material": False,
        "stop_reason": "no_executable_feedback_plan",
    }
    out = enrich_metrics_diagnostic_row(row, extra)
    assert out["quality_gate_reason_codes"] == ["complex_answer_not_deep_enough"]
    assert out["stop_reason"] == "no_executable_feedback_plan"
    assert out["metrics_would_answer_refine"] is True
    assert out["metrics_partial_bucket"] == "answer_only_gap"


def test_build_complex_failure_breakdown():
    rows = [
        {
            "id": "a",
            "is_complex_task": True,
            "task_status": "partial",
            "metrics_partial_bucket": "answer_only_gap",
            "metrics_would_answer_refine": True,
        },
        {
            "id": "b",
            "is_complex_task": True,
            "task_status": "succeeded",
        },
    ]
    bd = build_complex_failure_breakdown(rows)
    assert bd["complex_total"] == 2
    assert bd["complex_partial"] == 1
    assert bd["partial_buckets"]["answer_only_gap"] == 1
    assert bd["would_answer_refine_ids"] == ["a"]
