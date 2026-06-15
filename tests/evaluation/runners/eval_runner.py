from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tests.evaluation.runners.eval_capability_extractors import (
    extract_common_exit_fields,
    extract_document_capability_fields,
    extract_kb_capability_fields,
    extract_video_capability_fields,
    extract_web_capability_fields,
)
from tests.evaluation.runners.eval_complex_agent_runner import run_v3_suite, v3_case_file
from tests.evaluation.runners.eval_assertions import (
    assert_allowed_value,
    assert_required_trace_fields,
    assert_task_status_is_canonical,
    check_must_not_happen_basic,
)
from tests.evaluation.runners.eval_case_loader import load_eval_cases
from tests.evaluation.runners.eval_fake_success_rules import (
    check_common_fake_success,
    check_document_fake_success,
    check_kb_fake_success,
    check_video_fake_success,
    check_web_fake_success,
)
from tests.evaluation.runners.eval_http_client import BackendUnavailableError, CaseTimeoutError, EvalHttpClient, ExecutionError
from tests.evaluation.runners.eval_result_writer import write_eval_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def v1_case_file() -> Path:
    return _repo_root() / "tests" / "evaluation" / "cases" / "v1_route_exit_state.yaml"


def v2_suite_case_files() -> dict[str, Path]:
    base = _repo_root() / "tests" / "evaluation" / "cases"
    return {
        "v2_capability_web": base / "v2_capability_web.yaml",
        "v2_capability_document": base / "v2_capability_document.yaml",
        "v2_capability_video": base / "v2_capability_video.yaml",
        "v2_capability_kb": base / "v2_capability_kb.yaml",
    }


def build_chat_payload(case: dict[str, Any]) -> dict[str, Any]:
    session_setup = case.get("session_setup") or {}
    payload = {
        "message": case["user_input"],
        "session_id": session_setup.get("session_id") or f"eval-{case['case_id']}",
        "use_knowledge": bool(session_setup.get("use_knowledge", case["case_id"].startswith("kb_"))),
    }
    if session_setup.get("confirm_long_web_video_asr") is not None:
        payload["confirm_long_web_video_asr"] = bool(session_setup["confirm_long_web_video_asr"])
    elif case["case_id"] == "long_video_confirm_required":
        payload["confirm_long_web_video_asr"] = False
    return payload


def extract_actual_fields(response: dict[str, Any]) -> dict[str, Any]:
    return extract_common_exit_fields(response)


def _extract_capability_fields(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    category = str(case.get("category") or "")
    if category == "web":
        return extract_web_capability_fields(response)
    if category == "document":
        return extract_document_capability_fields(response)
    if category == "video":
        return extract_video_capability_fields(response)
    if category == "kb":
        return extract_kb_capability_fields(response)
    return {}


def _missing_fields(actual: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field_name in ("task_status", "lane"):
        if actual.get(field_name) in (None, ""):
            missing.append(field_name)
    return missing


def _assert_equal(actual_value: Any, expected_value: Any, field_name: str) -> None:
    if actual_value != expected_value:
        raise ValueError(f"{field_name}={actual_value!r} does not match expected {expected_value!r}")


def evaluate_case(case: dict[str, Any], client: EvalHttpClient) -> dict[str, Any]:
    expected = case.get("expected") or {}
    failed_assertions: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    try:
        response = client.post_chat_agno(build_chat_payload(case))
        actual = extract_actual_fields(response)
        actual.update(_extract_capability_fields(case, response))
    except (BackendUnavailableError, CaseTimeoutError, ExecutionError) as exc:
        note = "backend_unavailable" if isinstance(exc, BackendUnavailableError) else "case_timeout" if isinstance(exc, CaseTimeoutError) else "execution_error"
        return {
            "case_id": case["case_id"],
            "passed": False,
            "failed_assertions": [str(exc)],
            "warnings": [],
            "missing_fields": [],
            "actual": None,
            "expected": expected,
            "notes": [note],
            "error_type": note,
        }

    missing_fields = _missing_fields(actual)
    for field_name in missing_fields:
        failed_assertions.append(f"{case['case_id']}: missing stable field {field_name}")

    checks: list[tuple[str, Any]] = [
        ("task_status", lambda: assert_task_status_is_canonical(actual.get("task_status"))),
    ]

    allowed_map = (
        ("lane", expected.get("allowed_lanes")),
        ("mode", expected.get("allowed_modes")),
        ("task_status", expected.get("allowed_task_status")),
        ("pending_kind", expected.get("allowed_pending_kinds")),
        ("primary_path", expected.get("allowed_primary_paths")),
    )
    for field_name, allowed_values in allowed_map:
        if allowed_values:
            checks.append(
                (
                    field_name,
                    lambda field_name=field_name, allowed_values=allowed_values: assert_allowed_value(
                        actual.get(field_name), allowed_values, field_name
                    ),
                )
            )

    warning_assertions = expected.get("warning_assertions") or {}
    required_trace_fields = (
        warning_assertions.get("required_trace_fields")
        or expected.get("required_trace_fields")
        or []
    )
    if required_trace_fields:
        try:
            assert_required_trace_fields(actual.get("extra"), required_trace_fields)
        except ValueError as exc:
            warnings.append(str(exc))

    if "expected_insufficient_evidence" in expected and expected.get("expected_insufficient_evidence") is not None:
        checks.append(
            (
                "insufficient_evidence",
                lambda: _assert_equal(
                    actual.get("insufficient_evidence"),
                    expected.get("expected_insufficient_evidence"),
                    "insufficient_evidence",
                ),
            )
        )

    for check_name, check in checks:
        try:
            check()
        except AssertionError:
            failed_assertions.append(f"{check_name} assertion failed")
        except ValueError as exc:
            failed_assertions.append(str(exc))

    result = {
        "case_id": case["case_id"],
        "passed": not failed_assertions,
        "failed_assertions": failed_assertions,
        "warnings": warnings,
        "missing_fields": missing_fields,
        "actual": actual,
        "expected": expected,
        "notes": notes,
        "error_type": None,
    }

    hard_failures, rule_warnings, matched_rules = check_must_not_happen_basic(
        result,
        case.get("must_not_happen") or [],
        must_not_happen_rule_ids=case.get("must_not_happen_rule_ids") or [],
    )
    result["failed_assertions"].extend(hard_failures)
    result["warnings"].extend(rule_warnings)
    result["matched_rule_catalog"] = matched_rules
    result["configured_rule_ids"] = [item["rule_id"] for item in matched_rules]
    result["executed_rule_ids"] = [item["rule_id"] for item in matched_rules if item.get("executed") == "true"]
    result["matched_hard_rule_ids"] = [
        item["rule_id"] for item in matched_rules if item.get("outcome") == "matched_hard_fail"
    ]
    result["matched_warning_rule_ids"] = [
        item["rule_id"] for item in matched_rules if item.get("outcome") == "matched_warning"
    ]
    if hard_failures:
        result["passed"] = False

    fake_success_warnings = check_common_fake_success(case, actual)
    category = str(case.get("category") or "")
    if category == "web":
        fake_success_warnings.extend(check_web_fake_success(case, actual))
    elif category == "document":
        fake_success_warnings.extend(check_document_fake_success(case, actual))
    elif category == "video":
        fake_success_warnings.extend(check_video_fake_success(case, actual))
    elif category == "kb":
        fake_success_warnings.extend(check_kb_fake_success(case, actual))
    result["warnings"].extend(fake_success_warnings)
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    if fake_success_warnings:
        result["passed"] = False

    return result


def _case_results_for_files(case_files: list[Path], http_client: EvalHttpClient) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for case_file in case_files:
        for case in load_eval_cases(case_file):
            case_results.append(evaluate_case(case, http_client))
    return case_results


def run_suite(
    *,
    suite_name: str,
    case_file: str | Path | None = None,
    client: EvalHttpClient | None = None,
) -> dict[str, Any]:
    http_client = client or EvalHttpClient()
    started_at = datetime.now().isoformat(timespec="seconds")
    health = http_client.health_check()
    if suite_name == "v3_complex_agent":
        return run_v3_suite(suite_name=suite_name, case_file=case_file or v3_case_file(), client=http_client)
    if suite_name == "v2_capability_all":
        case_results = _case_results_for_files(list(v2_suite_case_files().values()), http_client)
    else:
        case_results = _case_results_for_files([Path(case_file or v1_case_file())], http_client)
    finished_at = datetime.now().isoformat(timespec="seconds")

    fake_success_warnings = [warning for case in case_results for warning in case.get("warnings") or []]
    missing_field_warnings = [
        warning
        for case in case_results
        for warning in case.get("warnings") or []
        if "missing field" in warning
    ]
    external_dependency_warnings = [
        f"{case['case_id']}: external_dependency_required"
        for case in case_results
        if any(
            token in " ".join((case.get("failed_assertions") or []) + (case.get("warnings") or [])).lower()
            for token in ("provider", "cookie", "external_dependency_required", "backend_returned")
        )
    ]
    report_paths = write_eval_report(
        suite_name=suite_name,
        backend_base_url=http_client.base_url,
        started_at=started_at,
        finished_at=finished_at,
        case_results=case_results,
        fake_success_warnings=fake_success_warnings,
        missing_field_warnings=missing_field_warnings,
        external_dependency_warnings=external_dependency_warnings,
    )
    return {
        "suite_name": suite_name,
        "health": health,
        "case_results": case_results,
        "report_paths": report_paths,
        "backend_base_url": http_client.base_url,
        "started_at": started_at,
        "finished_at": finished_at,
    }
