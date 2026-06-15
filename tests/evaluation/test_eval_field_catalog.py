from __future__ import annotations

from tests.evaluation.runners.eval_complex_agent_runner import _evaluate_hard_assertions
from tests.evaluation.runners.eval_field_catalog import classify_field


def test_field_catalog_classifies_stable_contract_fields() -> None:
    assert classify_field("task_status").tier == "stable_contract"
    assert classify_field("primary_path").tier == "stable_contract"
    assert classify_field("pending_kind").tier == "stable_contract"


def test_field_catalog_classifies_fragile_observability_fields() -> None:
    assert classify_field("extra.web_primary_source").tier == "fragile_observability"
    assert classify_field("v6_main_pan_renwu").tier == "fragile_observability"
    assert classify_field("quality_gate.reason_codes").tier == "fragile_observability"


def test_field_catalog_keeps_contextual_fields_out_of_fragile_bucket() -> None:
    assert classify_field("quality_gate").tier == "contextual"
    assert classify_field("material_sufficiency").tier == "contextual"
    assert classify_field("web_primary_source").tier == "contextual"
    assert classify_field("transcript_source").tier == "contextual"


def test_v3_hard_assertions_keep_fragile_fields_as_warning_only() -> None:
    case = {
        "expected": {
            "hard_assertions": {
                "must_have_one_of": [
                    "v6_main_pan_renwu",
                ]
            }
        }
    }
    failures, warnings = _evaluate_hard_assertions(
        case,
        common={"task_status": "partial"},
        aggregate_actual={},
    )
    assert failures == []
    assert warnings
    assert "fragile must_have_one_of fields" in warnings[0]


def test_v3_hard_assertions_still_fail_when_stable_fields_are_missing() -> None:
    case = {
        "expected": {
            "hard_assertions": {
                "must_have_one_of": [
                    "primary_path",
                    "quality_gate",
                ]
            }
        }
    }
    failures, warnings = _evaluate_hard_assertions(
        case,
        common={"task_status": "partial"},
        aggregate_actual={},
    )
    assert failures == ["none of stable must_have_one_of fields observable: primary_path, quality_gate"]
    assert warnings == []
