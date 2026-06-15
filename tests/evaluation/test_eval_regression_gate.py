from __future__ import annotations

from pathlib import Path

from scripts.evaluation.render_eval_overview import (
    KNOWN_ISSUE_CASE_MAP,
    build_regression_overview,
    classify_suite_result,
    render_regression_overview,
)


def test_known_issue_mapping_contains_current_known_issues() -> None:
    assert KNOWN_ISSUE_CASE_MAP["video_total_failure"] == "KI-V2-001"
    assert KNOWN_ISSUE_CASE_MAP["background_task_followup_flow"] == "KI-V2.5-001"
    assert KNOWN_ISSUE_CASE_MAP["continue_without_context_flow"] == "KI-V2.5-002"
    assert KNOWN_ISSUE_CASE_MAP["complex_document_reasoning"] == "KI-V3-001"
    assert KNOWN_ISSUE_CASE_MAP["complex_interview_explanation"] == "KI-V3-002"


def test_failed_case_matches_known_issue() -> None:
    suite_result = {
        "suite_name": "v3_complex_agent",
        "case_results": [{"case_id": "complex_document_reasoning", "passed": False}],
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "pass_rate": 0.0,
        "report_paths": {},
    }
    classified = classify_suite_result(suite_result)
    assert classified["status"] == "failed_known_issue"
    assert classified["known_issue_matches"][0]["issue_id"] == "KI-V3-001"


def test_unknown_failed_case_enters_unknown_failures() -> None:
    suite_result = {
        "suite_name": "v3_complex_agent",
        "case_results": [{"case_id": "some_new_failure", "passed": False}],
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "pass_rate": 0.0,
        "report_paths": {},
    }
    classified = classify_suite_result(suite_result)
    assert classified["status"] == "failed_unknown"
    assert classified["unknown_failures"] == ["some_new_failure"]


def test_case_timeout_is_not_classified_as_unknown_failure() -> None:
    suite_result = {
        "suite_name": "v3_complex_agent",
        "case_results": [{"case_id": "complex_insufficient_evidence", "passed": False, "error_type": "case_timeout"}],
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "pass_rate": 0.0,
        "report_paths": {},
    }
    classified = classify_suite_result(suite_result)
    assert classified["status"] == "case_timeout"
    assert classified["case_timeouts"] == ["complex_insufficient_evidence"]
    assert classified["unknown_failures"] == []


def test_execution_error_is_not_classified_as_unknown_failure() -> None:
    suite_result = {
        "suite_name": "v2_capability_all",
        "case_results": [{"case_id": "some_eval_failure", "passed": False, "error_type": "execution_error"}],
        "total_cases": 1,
        "passed_cases": 0,
        "failed_cases": 1,
        "pass_rate": 0.0,
        "report_paths": {},
    }
    classified = classify_suite_result(suite_result)
    assert classified["status"] == "execution_error"
    assert classified["execution_errors"] == ["some_eval_failure"]
    assert classified["unknown_failures"] == []


def test_regression_overview_contains_required_fields() -> None:
    overview = build_regression_overview(
        [
            {
                "suite_name": "v3_complex_agent",
                "case_results": [{"case_id": "complex_document_reasoning", "passed": False}],
                "total_cases": 1,
                "passed_cases": 0,
                "failed_cases": 1,
                "pass_rate": 0.0,
                "report_paths": {},
            }
        ],
        backend_status="ok",
    )
    assert overview["version_name"] == "V4：Report + Regression Gate"
    assert "suite_results" in overview
    assert "known_issues" in overview
    assert "known_issue_matches" in overview
    assert "unknown_failures" in overview
    assert "case_timeouts" in overview
    assert "execution_errors" in overview
    assert "final_verdict" in overview


def test_regression_overview_markdown_can_be_generated() -> None:
    paths = render_regression_overview(
        regression_results=[
            {
                "suite_name": "v3_complex_agent",
                "case_results": [{"case_id": "complex_document_reasoning", "passed": False}],
                "total_cases": 1,
                "passed_cases": 0,
                "failed_cases": 1,
                "pass_rate": 0.0,
                "report_paths": {},
            }
        ],
        backend_status="ok",
        generated_at="2026-06-13T14:00:00",
    )
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()


def test_backend_unavailable_is_not_faked_as_passed() -> None:
    overview = build_regression_overview(
        [
            {
                "suite_name": "v1_route_exit_state",
                "backend_unavailable": True,
                "report_paths": {},
                "total_cases": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "pass_rate": 0.0,
            }
        ],
        backend_status="backend_unavailable",
    )
    assert overview["suite_results"][0]["status"] == "backend_unavailable"


def test_known_issue_is_not_rewritten_to_passed() -> None:
    suite_result = {
        "suite_name": "v2_5_multiturn_state",
        "flow_results": [{"case_id": "background_task_followup_flow", "passed": False}],
        "total_flows": 1,
        "passed_flows": 0,
        "failed_flows": 1,
        "pass_rate": 0.0,
        "report_paths": {},
    }
    classified = classify_suite_result(suite_result)
    assert classified["status"] == "failed_known_issue"
