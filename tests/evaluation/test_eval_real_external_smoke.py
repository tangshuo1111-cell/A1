from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.evaluation import run_eval_suite
from scripts.evaluation.render_eval_overview import KNOWN_ISSUE_CASE_MAP
from tests.evaluation.runners.eval_real_external_runner import (
    load_real_external_cases,
    real_external_case_file,
    run_capability_cases,
    run_dependency_preflight,
    run_optional_regression,
    run_real_external_smoke_suite,
)
from tests.evaluation.runners.eval_real_external_status import (
    REAL_EXTERNAL_STATUSES,
    aggregate_capability_summary,
    build_sanitized_summary,
    compute_exit_code,
    dependency_missing_reason_from_errors,
    is_dependency_missing_error,
    make_entry,
    resolve_product_failure,
    sanitize_text,
)
from tests.evaluation.runners.eval_result_writer import write_real_external_smoke_report


REPO_ROOT = Path(__file__).resolve().parents[2]


# G1
def test_real_external_suite_is_registered_only_in_run_eval_suite() -> None:
    source = inspect.getsource(run_eval_suite.main)
    assert "real_external_smoke" in source
    assert "run_real_external_smoke_suite" in source
    scripts = list((REPO_ROOT / "scripts" / "evaluation").glob("*.py"))
    standalone = []
    for path in scripts:
        if path.name == "run_eval_suite.py":
            continue
        text = path.read_text(encoding="utf-8")
        if 'choices=[' in text and "real_external_smoke" in text and "argparse" in text:
            standalone.append(path.name)
    assert standalone == []


# G2
def test_real_external_status_does_not_enter_product_contract() -> None:
    product_statuses = {"succeeded", "pending", "blocked", "partial", "failed"}
    assert REAL_EXTERNAL_STATUSES.isdisjoint(product_statuses)
    for status in REAL_EXTERNAL_STATUSES:
        assert status not in product_statuses


# G3
def test_real_external_does_not_modify_chat_contract() -> None:
    runner_source = (REPO_ROOT / "tests" / "evaluation" / "runners" / "eval_real_external_runner.py").read_text(encoding="utf-8")
    assert 'task_status = "not_configured"' not in runner_source
    assert "ChatTurnResult(" not in runner_source
    openapi = REPO_ROOT / "docs" / "current" / "openapi.json"
    assert openapi.exists()


# G4
def test_real_external_does_not_change_known_issue_mapping() -> None:
    assert "video_total_failure" in KNOWN_ISSUE_CASE_MAP
    assert "complex_document_reasoning" in KNOWN_ISSUE_CASE_MAP
    for status in REAL_EXTERNAL_STATUSES:
        assert status not in KNOWN_ISSUE_CASE_MAP.values()


# G5
def test_real_external_uses_eval_writer_extension_not_second_writer() -> None:
    runners_dir = REPO_ROOT / "tests" / "evaluation" / "runners"
    extra_writers = [p.name for p in runners_dir.glob("*real_external*writer*.py")]
    assert extra_writers == []
    from tests.evaluation.runners import eval_result_writer

    assert hasattr(eval_result_writer, "write_real_external_smoke_report")


# G6
def test_real_external_not_in_default_ci() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "real_external_smoke" not in ci
    assert "not real_external" in ci
    this_file = Path(__file__).read_text(encoding="utf-8")
    decorator_lines = [line for line in this_file.splitlines() if line.strip().startswith("@pytest.mark.real_external")]
    assert decorator_lines == []


# G7
def test_real_external_report_sanitizer_blocks_secrets() -> None:
    dirty = "sk-abcdefghijklmnopqrstuvwxyz Bearer secret-token cookie=abc123 C:\\Users\\Admin\\secret"
    clean = sanitize_text(dirty)
    assert "sk-" not in clean
    assert "secret-token" not in clean
    assert "cookie=abc123" not in clean
    assert "Admin" not in clean


# G8
def test_real_external_not_configured_is_not_passed_or_failed() -> None:
    cases = [
        make_entry(case_id="a", status="not_configured", configured=False),
        make_entry(case_id="b", status="skipped", configured=False),
        make_entry(case_id="c", status="dependency_missing", configured=False),
        make_entry(case_id="d", status="configured_and_passed", configured=True),
        make_entry(
            case_id="e",
            status="configured_and_failed",
            configured=True,
            reason="credential_invalid",
            product_failure=resolve_product_failure(status="configured_and_failed", reason="credential_invalid"),
        ),
    ]
    summary = aggregate_capability_summary(cases)
    assert summary["passed_configured_cases_count"] == 1
    assert summary["failed_cases_count"] == 0
    assert summary["not_configured_cases_count"] == 1
    assert summary["skipped_cases_count"] == 1


# G9
def test_real_external_optional_regression_is_not_default_case() -> None:
    cases = load_real_external_cases()
    assert all(c["case_id"] != "regression_all" for c in cases)
    with patch.dict(os.environ, {}, clear=True):
        opt = run_optional_regression(backend_ok=True)
    assert opt["enabled"] is False


# G10
def test_real_external_product_failure_only_on_honesty_violations() -> None:
    assert resolve_product_failure(status="configured_and_failed", reason="fake_success_detected") is True
    assert resolve_product_failure(status="configured_and_failed", reason="credential_invalid") is False
    assert resolve_product_failure(status="external_timeout", reason="provider_timeout") is False


def test_real_external_smoke_case_file_has_seven_cases() -> None:
    cases = load_real_external_cases()
    assert len(cases) == 7
    ids = {c["case_id"] for c in cases}
    assert ids == {
        "llm_real_minimal",
        "web_static_real",
        "document_fixture_real",
        "kb_real_roundtrip",
        "video_subtitle_probe_real",
        "asr_real_short_audio",
        "ocr_real_sample",
    }


def test_backend_unavailable_exit_code_two() -> None:
    code = compute_exit_code(backend_unavailable=True, configured_cases_count=0)
    assert code == 2


def test_not_configured_only_exit_zero() -> None:
    code = compute_exit_code(product_failure_cases_count=0)
    assert code == 0


def test_write_real_external_smoke_report_generates_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "tests.evaluation.runners.eval_result_writer._report_paths",
        lambda _suite, _ts: (tmp_path / "r.json", tmp_path / "r.md"),
    )
    report = {
        "suite_name": "real_external_smoke",
        "suite_role": "real_capability_reproducibility",
        "version_note": "V4 post-hardening; not a new eval version",
        "backend_base_url": "http://127.0.0.1:8000",
        "dependency_preflight": [],
        "capability_cases": [
            make_entry(case_id="llm_real_minimal", status="not_configured", configured=False, reason="missing_llm_key"),
        ],
        "optional_regression": {"enabled": False},
        "summary": aggregate_capability_summary([
            make_entry(case_id="llm_real_minimal", status="not_configured", configured=False),
        ]),
        "final_verdict": "environment_not_ready",
        "recommendations": ["Configure keys"],
    }
    report["sanitized_summary"] = build_sanitized_summary(report)
    paths = write_real_external_smoke_report(report, timestamp_text="20260615_180000")
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["suite_name"] == "real_external_smoke"
    assert "sk-" not in payload["sanitized_summary"]


def test_run_real_external_smoke_suite_with_mocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "tests.evaluation.runners.eval_result_writer._report_paths",
        lambda _suite, _ts: (tmp_path / "r.json", tmp_path / "r.md"),
    )
    mock_client = MagicMock()
    mock_client.base_url = "http://127.0.0.1:8000"
    mock_client.health_check.side_effect = Exception("down")

    with patch(
        "tests.evaluation.runners.eval_real_external_runner.run_dependency_preflight",
        return_value=[make_entry(case_id="backend", status="backend_unavailable", configured=False, reason="backend_unreachable")],
    ), patch(
        "tests.evaluation.runners.eval_real_external_runner.run_capability_cases",
        return_value=[make_entry(case_id="document_fixture_real", status="configured_and_passed", configured=True)],
    ), patch(
        "tests.evaluation.runners.eval_real_external_runner.run_optional_regression",
        return_value={"enabled": False, "reason": "REAL_EXTERNAL_RUN_REGRESSION not set"},
    ):
        result = run_real_external_smoke_suite(client=mock_client)
    assert result["suite_name"] == "real_external_smoke"
    assert result["exit_code"] in {0, 2}
    assert "report_paths" in result


def test_capability_timeout_does_not_crash_runner() -> None:
    mock_client = MagicMock()
    cases = [{"case_id": "web_static_real", "user_input": "x", "session_setup": {}}]

    def _timeout(case, client, backend_ok):
        return make_entry(case_id="web_static_real", status="external_timeout", configured=True, reason="provider_timeout")

    with patch.dict(
        "tests.evaluation.runners.eval_real_external_runner._CAPABILITY_RUNNERS",
        {"web_static_real": _timeout},
    ):
        results = run_capability_cases(cases, mock_client, backend_ok=True)
    assert results[0]["status"] == "external_timeout"


def test_fake_llm_skips_llm_case(monkeypatch) -> None:
    monkeypatch.setenv("LIGHT_MAQA_FAKE_LLM", "1")
    case = {"case_id": "llm_real_minimal", "user_input": "1+1=?"}
    from tests.evaluation.runners.eval_real_external_runner import run_capability_llm_real_minimal

    result = run_capability_llm_real_minimal(case)
    assert result["status"] == "skipped"
    assert result["reason"] == "fake_llm_enabled"
    assert result["product_failure"] is False


def test_dependency_error_codes_map_to_dependency_missing_status() -> None:
    assert is_dependency_missing_error("tool_not_found") is True
    assert is_dependency_missing_error("dependency_not_installed") is True
    assert is_dependency_missing_error("parser_dependency_missing") is True
    assert is_dependency_missing_error("credential_invalid") is False
    assert dependency_missing_reason_from_errors(["tool_not_found", "parse_failed"]) == "tool_not_found"
    assert dependency_missing_reason_from_errors(["parse_failed"]) is None


def test_document_fixture_tool_not_found_is_dependency_missing(monkeypatch) -> None:
    from types import SimpleNamespace

    from tests.evaluation.runners.eval_real_external_runner import run_capability_document_fixture_real

    fixture_rel = "tests/evaluation/fixtures/documents/sample.txt"
    monkeypatch.setattr(
        "tests.evaluation.runners.eval_real_external_runner._repo_root",
        lambda: REPO_ROOT,
    )

    def _fake_call_tool(tool_name: str, **kwargs):
        return SimpleNamespace(status="failed", text="", error_code="tool_not_found", failure_reason="tool missing")

    monkeypatch.setattr(
        "tools.document.registry.call_tool",
        _fake_call_tool,
    )
    result = run_capability_document_fixture_real({"fixtures": [fixture_rel]})
    assert result["status"] == "dependency_missing"
    assert result["configured"] is False
    assert result["reason"] == "tool_not_found"
    assert result["product_failure"] is False
