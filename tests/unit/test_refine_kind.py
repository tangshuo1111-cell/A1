"""Unit tests for RefineKind contract and metrics diagnostic helpers."""

from __future__ import annotations

import pytest

from application.chat.refine_kind import (
    answer_only_refine_reason_codes,
    build_answer_only_executor_hint,
    build_complex_failure_breakdown,
    classify_partial_bucket,
    enrich_metrics_diagnostic_row,
    exit_insufficient_evidence,
    is_answer_only_refine_bundle,
    narrow_general_reasoning_gate_reasons,
    narrow_kb_insufficient_reasons,
    reconcile_answer_only_turn_facts,
    resolve_refine_kind,
    would_answer_only_refine_apply,
)
from application.chat.chat_contracts import QualityGateResult, TurnExitEnvelope
from application.chat.pending_kind import PendingKind
from application.chat.turn_facts import TurnFacts
from config.feature_flags import FEATURE_FLAGS


@pytest.fixture(autouse=True)
def _restore_flags():
    saved = dict(FEATURE_FLAGS)
    yield
    FEATURE_FLAGS.clear()
    FEATURE_FLAGS.update(saved)


def test_narrow_kb_insufficient_when_flag_off():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = False
    reasons = ["kb_insufficient", "answer_too_shallow"]
    assert narrow_kb_insufficient_reasons(
        reasons, lane="general", use_knowledge=False, retrieved_chunks_count=0
    ) == reasons


def test_narrow_general_reasoning_drops_material_and_limitations():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    out = narrow_general_reasoning_gate_reasons(
        ["answer_too_shallow", "limitations_present", "material_insufficient"],
        ["当前未从知识库检索到可用片段，也未获得可用的外部网页证据"],
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=0,
    )
    assert out == ["answer_too_shallow"]


def test_narrow_general_reasoning_keeps_honesty_limitations():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    out = narrow_general_reasoning_gate_reasons(
        ["limitations_present", "answer_too_shallow"],
        ["video_total_failure: 无法解析视频"],
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=0,
    )
    assert "limitations_present" in out


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
        lane="kb",
        use_knowledge=True,
        retrieved_chunks_count=1,
    ) == "material"


def test_answer_only_despite_material_insufficiency_on_general_lane():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    lims = ["当前未从知识库检索到可用片段，也未获得可用的外部网页证据"]
    assert resolve_refine_kind(
        need_second_round=True,
        need_more_material=False,
        reason_codes=("answer_too_shallow",),
        insufficient_evidence=True,
        pending_kind=None,
        answer_text="结论：现有材料不足，无法确认。",
        limitations=lims,
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=0,
    ) == "answer_only"


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


def test_build_answer_only_executor_hint_forbids_insufficiency_template():
    hint = build_answer_only_executor_hint(reason_codes=("answer_too_shallow", "decision_not_made"))
    assert "禁止" in hint
    assert "材料不足" in hint
    assert "decision_not_made" in hint or "明确推荐" in hint


def test_is_answer_only_refine_bundle_from_trace():
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    bundle = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.0,
            bukong_xinhao="zu",
            laiyuan_zhu="wu",
            use_kb=False,
            use_web=False,
            que_shenme="",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="sufficient",
        bundle_id="b-ao",
        autonomy_events=[
            {
                "requested_action": "answer_only_regenerate",
                "payload": {
                    "refine_kind": "answer_only",
                    "refine_reason_codes": ["answer_too_shallow"],
                },
            }
        ],
    )
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    assert is_answer_only_refine_bundle(bundle)
    assert answer_only_refine_reason_codes(bundle) == ("answer_too_shallow",)


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


def test_narrow_general_reasoning_drops_material_with_weak_incidental_chunks():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    out = narrow_general_reasoning_gate_reasons(
        ["material_insufficient", "answer_too_shallow"],
        [],
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=1,
        kb_evidence_tier="weak",
    )
    assert out == ["answer_too_shallow"]


def test_narrow_general_reasoning_keeps_material_with_strong_chunks():
    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    out = narrow_general_reasoning_gate_reasons(
        ["material_insufficient", "answer_too_shallow"],
        [],
        lane="general",
        use_knowledge=False,
        retrieved_chunks_count=1,
        kb_evidence_tier="strong",
    )
    assert out == ["material_insufficient", "answer_too_shallow"]


def test_reconcile_answer_only_turn_facts_clears_stale_partial():
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    bundle = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.0,
            bukong_xinhao="zu",
            laiyuan_zhu="wu",
            use_kb=False,
            use_web=False,
            que_shenme="",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="sufficient",
        bundle_id="b-rec",
        final_answer_based_on_round="round_1",
        execution_status="partial",
        negotiation_trace={"complex_pending_kind": "partial_pending"},
        autonomy_events=[
            {
                "requested_action": "answer_only_regenerate",
                "payload": {"refine_kind": "answer_only", "refine_reason_codes": ["answer_too_shallow"]},
            }
        ],
    )
    facts = TurnFacts(
        router_lane="general",
        effective_mode="complex",
        executor_profile="complex",
        pending_kind=PendingKind.PARTIAL_PENDING,
        material_sufficiency="insufficient",
        quality_gate=QualityGateResult(pass_=True, reason_codes=()),
    )
    out = reconcile_answer_only_turn_facts(facts, bundle=bundle, use_knowledge=False)
    assert out.pending_kind == PendingKind.NONE
    assert out.material_sufficiency == "sufficient"
    assert out.answer_only_exit_reconcile is True
    assert out.quality_gate is not None
    assert out.quality_gate.pass_ is True


def test_reconcile_skips_kb_scope():
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
    bundle = AgnoMaterialBundle(
        knowledge_block="kb",
        web_block=None,
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="low",
        insufficiency_signal="still_empty_after_gather",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.1,
            bukong_xinhao="bu",
            laiyuan_zhu="kb",
            use_kb=True,
            use_web=False,
            que_shenme="",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="insufficient",
        bundle_id="b-kb",
        retrieved_chunks=[object()],
        final_answer_based_on_round="round_1",
        autonomy_events=[
            {
                "requested_action": "answer_only_regenerate",
                "payload": {"refine_kind": "answer_only"},
            }
        ],
    )
    facts = TurnFacts(
        router_lane="kb",
        pending_kind=PendingKind.PARTIAL_PENDING,
        material_sufficiency="insufficient",
        quality_gate=QualityGateResult(pass_=True, reason_codes=()),
    )
    out = reconcile_answer_only_turn_facts(facts, bundle=bundle, use_knowledge=True)
    assert out is facts


def test_exit_insufficient_evidence_false_after_reconcile_envelope_fields():
    env = TurnExitEnvelope(
        task_status="succeeded",
        pending_kind=None,
        primary_path="complex_rag_answer",
        mode="complex",
        executor_profile="complex",
        router_lane="general",
        material_sufficiency="sufficient",
        quality_gate={"pass": True, "reason_codes": []},
        winner_rule="default_success",
        trace={},
    )
    assert exit_insufficient_evidence(env) is False


def test_exit_insufficient_evidence_true_when_material_stale():
    env = TurnExitEnvelope(
        task_status="succeeded",
        pending_kind=None,
        primary_path="complex_rag_answer",
        mode="complex",
        executor_profile="complex",
        router_lane="general",
        material_sufficiency="insufficient",
        quality_gate={"pass": True, "reason_codes": ["kb_insufficient"]},
        winner_rule="default_success",
        trace={},
    )
    assert exit_insufficient_evidence(env) is True
