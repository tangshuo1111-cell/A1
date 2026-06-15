from __future__ import annotations

from pathlib import Path

import pytest

from tests.evaluation.runners.eval_assertions import assert_task_status_is_canonical
from tests.evaluation.runners.eval_http_client import BackendUnavailableError
from tests.evaluation.runners.eval_result_writer import write_eval_report
from tests.evaluation.runners.eval_runner import evaluate_case, run_suite, v1_case_file
from tests.evaluation.runners.eval_case_loader import load_eval_cases


def test_v1_case_file_exists() -> None:
    assert v1_case_file().exists()


def test_v1_case_ids_are_unique() -> None:
    cases = load_eval_cases(v1_case_file())
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))


def test_v1_case_count_at_least_ten() -> None:
    assert len(load_eval_cases(v1_case_file())) >= 10


def test_each_case_has_must_not_happen() -> None:
    for case in load_eval_cases(v1_case_file()):
        assert case["must_not_happen"]


def test_each_case_uses_rule_only_judge() -> None:
    for case in load_eval_cases(v1_case_file()):
        assert case["judge"]["rule"] is True
        assert case["judge"]["llm_judge"] is False
        assert case["judge"]["human_review"] is False


@pytest.mark.parametrize("task_status", ["pending", "succeeded", "failed", "blocked", "partial"])
def test_canonical_task_status_accepts_valid_values(task_status: str) -> None:
    assert_task_status_is_canonical(task_status)


def test_canonical_task_status_rejects_insufficient() -> None:
    with pytest.raises(ValueError):
        assert_task_status_is_canonical("insufficient")


def test_result_writer_writes_json_and_markdown() -> None:
    paths = write_eval_report(
        suite_name="v1_route_exit_state",
        backend_base_url="http://127.0.0.1:8000",
        started_at="2026-06-12T12:00:00",
        finished_at="2026-06-12T12:00:01",
        case_results=[{"case_id": "c1", "passed": True, "failed_assertions": [], "warnings": [], "actual": {"task_status": "succeeded"}, "matched_rule_catalog": []}],
        fake_success_warnings=[],
        missing_field_warnings=[],
        timestamp_text="20260612_120000",
    )
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert "rule_execution_breakdown" in paths["json"].read_text(encoding="utf-8")
    assert "rule_coverage_summary" in paths["json"].read_text(encoding="utf-8")


class _MockClient:
    base_url = "http://127.0.0.1:8000"

    def __init__(self, response: dict | None = None, *, raise_on_post: Exception | None = None) -> None:
        self._response = response or {}
        self._raise_on_post = raise_on_post

    def health_check(self) -> dict:
        return {"status": "ok"}

    def post_chat_agno(self, payload: dict) -> dict:
        if self._raise_on_post is not None:
            raise self._raise_on_post
        return self._response


def test_runner_with_mock_client_produces_case_result() -> None:
    case = load_eval_cases(v1_case_file())[0]
    client = _MockClient(
        response={
            "ok": True,
            "answer": "RAG 是检索增强生成。",
            "task_status": "succeeded",
            "primary_path": "general_fast",
            "extra": {
                "lane": "general",
                "mode": "fast",
                "insufficient_evidence": False,
            },
        }
    )
    result = evaluate_case(case, client)
    assert result["case_id"] == case["case_id"]
    assert isinstance(result["passed"], bool)


def test_runner_accepts_warning_assertions_and_rule_ids() -> None:
    case = load_eval_cases(v1_case_file())[0]
    case["expected"]["warning_assertions"] = {"required_trace_fields": ["lane", "mode"]}
    case["must_not_happen_rule_ids"] = ["C_ROUTE_QUALITY"]
    client = _MockClient(
        response={
            "ok": True,
            "answer": "RAG 是检索增强生成。",
            "task_status": "succeeded",
            "primary_path": "general_fast",
            "extra": {
                "lane": "general",
                "mode": "fast",
                "insufficient_evidence": False,
            },
        }
    )
    result = evaluate_case(case, client)
    assert "matched_rule_catalog" in result
    assert any(item["rule_id"] == "C_ROUTE_QUALITY" for item in result["matched_rule_catalog"])


def test_backend_unavailable_handled_without_fake_success() -> None:
    case = load_eval_cases(v1_case_file())[0]
    result = evaluate_case(case, _MockClient(raise_on_post=BackendUnavailableError("backend_unavailable")))
    assert result["passed"] is False
    assert result["actual"] is None
    assert "backend_unavailable" in result["notes"]


def test_run_suite_with_mock_client_writes_report() -> None:
    client = _MockClient(
        response={
            "ok": True,
            "answer": "ok",
            "task_status": "partial",
            "primary_path": "agno_basic",
            "extra": {"lane": "general", "mode": "complex"},
        }
    )
    result = run_suite(suite_name="v1_route_exit_state_test", client=client)
    assert Path(result["report_paths"]["json"]).exists()
    assert Path(result["report_paths"]["markdown"]).exists()
