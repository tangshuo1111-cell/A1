from __future__ import annotations

from pathlib import Path

from tests.evaluation.runners.eval_capability_extractors import (
    extract_document_capability_fields,
    extract_kb_capability_fields,
    extract_video_capability_fields,
    extract_web_capability_fields,
)
from tests.evaluation.runners.eval_fake_success_rules import (
    check_document_fake_success,
    check_kb_fake_success,
    check_video_fake_success,
    check_web_fake_success,
)
from tests.evaluation.runners.eval_result_writer import write_eval_report
from tests.evaluation.runners.eval_runner import run_suite, v2_suite_case_files
from tests.evaluation.runners.eval_case_loader import load_eval_cases


def test_v2_case_files_exist() -> None:
    for path in v2_suite_case_files().values():
        assert path.exists()


def test_each_v2_case_file_has_at_least_four_cases() -> None:
    for path in v2_suite_case_files().values():
        assert len(load_eval_cases(path)) >= 4


def test_total_v2_case_count_at_least_sixteen() -> None:
    total = sum(len(load_eval_cases(path)) for path in v2_suite_case_files().values())
    assert total >= 16


def test_each_v2_case_has_rule_and_must_not_happen() -> None:
    for path in v2_suite_case_files().values():
        for case in load_eval_cases(path):
            assert case["must_not_happen"]
            assert case["judge"]["rule"] is True
            assert case["judge"]["llm_judge"] is False
            assert case["judge"]["human_review"] is False


def test_v2_capability_all_loads_all_suites() -> None:
    assert set(v2_suite_case_files().keys()) == {
        "v2_capability_web",
        "v2_capability_document",
        "v2_capability_video",
        "v2_capability_kb",
    }


def test_extractors_do_not_crash_on_missing_fields() -> None:
    response = {"ok": True, "extra": {}}
    assert isinstance(extract_web_capability_fields(response), dict)
    assert isinstance(extract_document_capability_fields(response), dict)
    assert isinstance(extract_video_capability_fields(response), dict)
    assert isinstance(extract_kb_capability_fields(response), dict)


def test_fake_success_rules_can_return_warning() -> None:
    case = {"case_id": "web_static_success", "user_input": "web", "category": "web"}
    assert check_web_fake_success(case, {"task_status": "succeeded"})
    assert check_document_fake_success({"case_id": "document_ocr_required_honesty", "user_input": "扫描 PDF"}, {"task_status": "succeeded"})
    assert check_video_fake_success({"case_id": "video_subtitle_or_transcript_success", "user_input": "video"}, {"task_status": "succeeded"})
    assert check_kb_fake_success({"case_id": "kb_no_hit_honesty", "user_input": "知识库"}, {"task_status": "succeeded"})


def test_result_writer_writes_capability_summary() -> None:
    paths = write_eval_report(
        suite_name="v2_capability_web",
        backend_base_url="http://127.0.0.1:8000",
        started_at="2026-06-12T12:00:00",
        finished_at="2026-06-12T12:00:01",
        case_results=[{"case_id": "web_static_success", "passed": True, "failed_assertions": [], "warnings": [], "actual": {"task_status": "succeeded", "extra": {}}}],
        fake_success_warnings=[],
        missing_field_warnings=[],
        external_dependency_warnings=[],
        timestamp_text="20260612_120001",
    )
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert "capability_summary" in Path(paths["json"]).read_text(encoding="utf-8")
    text = Path(paths["json"]).read_text(encoding="utf-8")
    assert "failure_breakdown" in text
    assert "warning_breakdown" in text


class _MockClient:
    base_url = "http://127.0.0.1:8000"

    def health_check(self) -> dict:
        return {"status": "ok"}

    def post_chat_agno(self, payload: dict) -> dict:
        return {
            "ok": True,
            "answer": "ok",
            "task_status": "partial",
            "primary_path": "agno_basic_v2_kb_v3_web",
            "extra": {"lane": "agno_basic_v2_kb_v3_web", "mode": "complex", "kb_hits": 1, "strategy_used": "auto:hybrid"},
        }


def test_mock_runner_supports_v2_all() -> None:
    result = run_suite(suite_name="v2_capability_all", client=_MockClient())
    assert Path(result["report_paths"]["json"]).exists()
