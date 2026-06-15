from __future__ import annotations

from tests.evaluation.runners.eval_assertions import check_must_not_happen_basic
from tests.evaluation.runners.eval_rule_catalog import RULE_CHECKERS, build_observed_fields, build_rule_coverage_summary


def test_build_observed_fields_keeps_answer_and_whitelisted_stable_fields() -> None:
    observed = build_observed_fields(
        {
            "answer": "根据知识库可以确定。",
            "task_status": "succeeded",
            "kb_hits": 2,
            "extra": {
                "background_task_id": "task-123",
                "v6_main_pan_renwu": "project_explain",
            },
        }
    )
    assert observed.answer == "根据知识库可以确定。"
    assert observed.get("kb_hits") == 2
    assert observed.get("background_task_id") == "task-123"
    assert observed.get("extra.v6_main_pan_renwu") == "project_explain"


def test_text_rule_compatibility_executes_through_rule_id_dispatch() -> None:
    result = {
        "actual": {
            "answer": "根据知识库明确得出，这是最终结论。",
            "task_status": "succeeded",
            "extra": {
                "lane": "kb",
            },
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        ["不能在 KB 无命中时说根据知识库得出"],
    )
    assert failures == ["KB grounding claimed without retrieval evidence"]
    assert warnings == []
    assert matched[0]["rule_id"] == "B_NO_KB_CLAIM_WITHOUT_EVIDENCE"
    assert matched[0]["executed"] == "true"
    assert matched[0]["outcome"] == "matched_hard_fail"


def test_warning_rule_returns_warning_not_hard_failure() -> None:
    result = {
        "actual": {
            "answer": "普通回答。",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "extra": {"lane": "video"},
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["C_ROUTE_QUALITY"],
    )
    assert failures == []
    assert warnings == ["specialized lane video resolved to direct_llm"]
    assert matched[0]["outcome"] == "matched_warning"


def test_unclassified_warning_rule_has_checker() -> None:
    result = {
        "actual": {
            "answer": "普通回答。",
            "task_status": "succeeded",
            "primary_path": "general_fast",
            "extra": {"lane": "general"},
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["C_UNCLASSIFIED_WARNING"],
    )
    assert failures == []
    assert warnings
    assert matched[0]["outcome"] == "matched_warning"


def test_all_catalog_rules_now_have_checkers() -> None:
    coverage = build_rule_coverage_summary()
    assert coverage["all_rules_total"] == coverage["all_rules_with_checker"]
    assert "C_UNCLASSIFIED_WARNING" in RULE_CHECKERS
    assert coverage["text_compat_still_active"] >= 0


def test_casual_previous_context_wording_does_not_hard_fail_without_promoted_signals() -> None:
    result = {
        "actual": {
            "answer": "刚才你问的问题我不太清楚，请再说明一下具体指哪段内容。",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "extra": {"lane": "general"},
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["A_NO_FAKE_CONTEXT"],
    )
    assert failures == []
    assert warnings == ["previous-context wording without promoted context signals"]
    assert matched[0]["outcome"] == "matched_warning"


def test_strong_previous_context_claim_hard_fails_without_promoted_signals() -> None:
    result = {
        "actual": {
            "answer": "已继续刚才那个内容的处理，当前结果如下。",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "extra": {"lane": "general"},
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["A_NO_FAKE_CONTEXT"],
    )
    assert failures == ["strong previous-context claim without promoted context signals"]
    assert warnings == []
    assert matched[0]["outcome"] == "matched_hard_fail"


def test_web_lane_success_without_observability_is_warning_not_hard_fail() -> None:
    result = {
        "actual": {
            "answer": "这是网页摘要。",
            "task_status": "succeeded",
            "lane": "web",
            "primary_path": "web_fast",
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["B_NO_WEB_CLAIM_WITHOUT_EVIDENCE"],
    )
    assert failures == []
    assert warnings == ["web lane succeeded without web observability signals"]
    assert matched[0]["outcome"] == "matched_warning"


def test_state_closure_without_kb_observability_is_warning_not_hard_fail() -> None:
    result = {
        "actual": {
            "answer": "已根据刚才保存的内容读取并整理如下。",
            "task_status": "succeeded",
            "primary_path": "kb_fast",
        }
    }
    failures, warnings, matched = check_must_not_happen_basic(
        result,
        [],
        must_not_happen_rule_ids=["A_NO_FAKE_STATE_CLOSURE"],
    )
    assert failures == []
    assert warnings == ["state closure claimed without kb hit observability"]
    assert matched[0]["outcome"] == "matched_warning"
