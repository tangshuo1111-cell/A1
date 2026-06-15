from __future__ import annotations

from pathlib import Path

import pytest

from tests.evaluation.runners.eval_multiturn_runner import evaluate_flow, load_multiturn_cases, run_multiturn_suite, v2_5_case_file
from tests.evaluation.runners.eval_result_writer import write_eval_multiturn_report
from tests.evaluation.runners.eval_state_closure_rules import check_common_state_honesty, check_save_without_pending
from tests.evaluation.runners.eval_state_extractors import (
    extract_common_state_fields,
    extract_commit_state_fields,
    extract_followup_state_fields,
    extract_pending_state_fields,
    extract_session_state_fields,
    extract_task_state_fields,
)


def test_v2_5_case_file_exists() -> None:
    assert v2_5_case_file().exists()


def test_v2_5_has_at_least_eight_flows() -> None:
    assert len(load_multiturn_cases()) >= 8


def test_each_flow_has_steps() -> None:
    for flow in load_multiturn_cases():
        assert flow["steps"]


def test_each_step_has_required_fields() -> None:
    for flow in load_multiturn_cases():
        for step in flow["steps"]:
            assert {"step_id", "user_input", "expected", "must_not_happen"}.issubset(step.keys())


def test_each_flow_uses_rule_only_judge() -> None:
    for flow in load_multiturn_cases():
        assert flow["judge"]["rule"] is True
        assert flow["judge"]["llm_judge"] is False
        assert flow["judge"]["human_review"] is False


def test_state_extractors_do_not_crash() -> None:
    response = {"ok": True, "extra": {}}
    assert isinstance(extract_common_state_fields(response), dict)
    assert isinstance(extract_session_state_fields(response), dict)
    assert isinstance(extract_pending_state_fields(response), dict)
    assert isinstance(extract_commit_state_fields(response), dict)
    assert isinstance(extract_task_state_fields(response), dict)
    assert isinstance(extract_followup_state_fields([], response), dict)


def test_state_closure_rules_detect_save_without_pending_fake_success() -> None:
    flow_result = {
        "case_id": "save_without_pending_flow",
        "steps": [{"step_id": "turn_1", "actual": {"answer": "保存成功", "commit_status": "succeeded"}}],
    }
    assert check_save_without_pending(flow_result)


def test_state_closure_rules_detect_illegal_insufficient_status() -> None:
    flow_result = {"case_id": "x", "steps": [{"step_id": "turn_1", "actual": {"task_status": "insufficient"}, "missing_fields": []}]}
    assert check_common_state_honesty(flow_result)


class _MockClient:
    base_url = "http://127.0.0.1:8000"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def health_check(self) -> dict:
        return {"status": "ok"}

    def post_chat_agno(self, payload: dict) -> dict:
        self.calls.append(payload)
        return {
            "ok": True,
            "session_id": payload["session_id"],
            "answer": f"echo:{payload['message']}",
            "task_status": "partial" if "知识库" in payload["message"] else "succeeded",
            "primary_path": "direct_llm",
            "extra": {"lane": "general", "mode": "fast", "pending_kind": None},
        }


def test_multiturn_runner_executes_steps_in_order() -> None:
    flow = load_multiturn_cases()[2]
    client = _MockClient()
    result = evaluate_flow(flow, client)
    assert len(result["steps"]) == len(flow["steps"])
    assert [call["message"] for call in client.calls] == [step["user_input"] for step in flow["steps"]]


def test_same_flow_uses_same_session_id() -> None:
    flow = load_multiturn_cases()[2]
    client = _MockClient()
    evaluate_flow(flow, client)
    assert len({call["session_id"] for call in client.calls}) == 1


def test_different_flows_do_not_share_session_id() -> None:
    flows = load_multiturn_cases()[:2]
    assert flows[0]["session_setup"]["session_id"] != flows[1]["session_setup"]["session_id"]


def test_multiturn_report_writer_writes_summary() -> None:
    paths = write_eval_multiturn_report(
        suite_name="v2_5_multiturn_state",
        backend_base_url="http://127.0.0.1:8000",
        started_at="2026-06-12T12:00:00",
        finished_at="2026-06-12T12:00:01",
        flow_results=[{"case_id": "f1", "case_name": "Flow", "passed": True, "session_id": "s1", "steps": [], "failed_assertions": [], "warnings": [], "state_markers": {}, "closure_checks": []}],
        missing_field_warnings=[],
        fake_state_success_warnings=[],
        timestamp_text="20260612_120002",
    )
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert "state_closure_summary" in Path(paths["json"]).read_text(encoding="utf-8")


def test_run_eval_suite_supports_v2_5_multiturn_state_with_mock_client() -> None:
    result = run_multiturn_suite(suite_name="v2_5_multiturn_state", client=_MockClient())
    assert Path(result["report_paths"]["json"]).exists()
