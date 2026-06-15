from __future__ import annotations

from pathlib import Path

from tests.evaluation.runners.eval_agent_collaboration_rules import (
    check_answer_grounded_in_material,
    check_common_agent_collaboration,
)
from tests.evaluation.runners.eval_agent_extractors import (
    extract_agent_common_fields,
    extract_answer_grounding_fields,
    extract_main_plan_fields,
    extract_middle_material_fields,
    extract_quality_gate_fields,
    extract_second_round_fields,
)
from tests.evaluation.runners.eval_complex_agent_runner import evaluate_v3_case, load_v3_cases, run_v3_suite, v3_case_file
from tests.evaluation.runners.eval_result_writer import write_eval_agent_report


def test_v3_case_file_exists() -> None:
    assert v3_case_file().exists()


def test_v3_has_at_least_eight_cases() -> None:
    assert len(load_v3_cases()) >= 8


def test_each_v3_case_has_expected_and_must_not_happen() -> None:
    for case in load_v3_cases():
        assert "expected" in case
        assert "must_not_happen" in case


def test_each_v3_case_uses_rule_only_judge() -> None:
    for case in load_v3_cases():
        assert case["judge"]["rule"] is True
        assert case["judge"]["llm_judge"] is False
        assert case["judge"]["human_review"] is False


def test_v3_extractors_do_not_crash_when_fields_missing() -> None:
    response = {"ok": True, "answer": "test", "extra": {}}
    assert isinstance(extract_agent_common_fields(response), dict)
    assert isinstance(extract_main_plan_fields(response), dict)
    assert isinstance(extract_middle_material_fields(response), dict)
    assert isinstance(extract_answer_grounding_fields(response), dict)
    assert isinstance(extract_quality_gate_fields(response), dict)
    assert isinstance(extract_second_round_fields(response), dict)


def test_rules_detect_claimed_material_without_signal() -> None:
    case = {"case_id": "complex_kb_project_explain"}
    actual = {
        "grounding": {"answer": "根据知识库明确得出，这个项目主链路完整如下。", "groundedness_markers": {"claims_strong_conclusion": True}},
        "material": {},
    }
    issues = check_answer_grounded_in_material(case, actual)
    assert issues


def test_rules_detect_illegal_insufficient_task_status() -> None:
    case = {"case_id": "complex_x"}
    actual = {"common": {"task_status": "insufficient"}}
    issues = check_common_agent_collaboration(case, actual)
    assert issues


class _MockClient:
    base_url = "http://127.0.0.1:8000"

    def health_check(self) -> dict:
        return {"status": "ok"}

    def post_chat_agno(self, payload: dict) -> dict:
        return {
            "ok": True,
            "session_id": payload["session_id"],
            "answer": "基于当前材料，我先给一个保守总结。",
            "task_status": "partial",
            "primary_path": "general_complex",
            "extra": {
                "mode": "complex",
                "router_lane": "general",
                "material_sufficiency": "partial",
                "quality_gate": {"pass": False, "need_second_round": True, "need_more_material": True, "reason_codes": ["kb_insufficient"]},
                "quality_gate.pass": False,
                "quality_gate.reason_codes": ["kb_insufficient"],
                "quality_gate.need_second_round": True,
                "quality_gate.need_more_material": True,
                "insufficient_evidence": True,
                "v6_main_pan_renwu": "project_explain",
                "v6_middle_pan_laiyuan": "kb+web",
                "v6_answer_pan_baoshou": 0.8,
            },
        }


def test_complex_agent_runner_generates_case_result_with_mock_client() -> None:
    case = load_v3_cases()[0]
    result = evaluate_v3_case(case, _MockClient())
    assert "case_id" in result
    assert "plan_markers" in result
    assert "material_markers" in result
    assert "grounding_markers" in result


def test_result_writer_outputs_agent_collaboration_summary() -> None:
    paths = write_eval_agent_report(
        suite_name="v3_complex_agent",
        backend_base_url="http://127.0.0.1:8000",
        started_at="2026-06-13T12:00:00",
        finished_at="2026-06-13T12:00:01",
        case_results=[
            {
                "case_id": "c1",
                "case_name": "Complex",
                "passed": True,
                "actual": {"common": {"task_status": "partial", "primary_path": "general_complex"}},
                "expected": {},
                "failed_assertions": [],
                "warnings": [],
                "missing_fields": [],
                "agent_markers": {},
                "plan_markers": {},
                "material_markers": {},
                "grounding_markers": {},
                "quality_gate_markers": {},
                "second_round_markers": {},
            }
        ],
        agent_collaboration_summary={"total_cases": 1},
        missing_field_warnings=[],
        grounding_warnings=[],
        fake_agent_success_warnings=[],
        timestamp_text="20260613_120003",
    )
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert "agent_collaboration_summary" in Path(paths["json"]).read_text(encoding="utf-8")


def test_run_eval_suite_supports_v3_complex_agent_with_mock_client() -> None:
    result = run_v3_suite(suite_name="v3_complex_agent", client=_MockClient())
    assert Path(result["report_paths"]["json"]).exists()
