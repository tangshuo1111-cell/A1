from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time
from typing import Any

import yaml

from tests.evaluation.runners.eval_assertions import assert_allowed_value, assert_required_trace_fields, assert_task_status_is_canonical
from tests.evaluation.runners.eval_http_client import BackendUnavailableError, CaseTimeoutError, EvalHttpClient, ExecutionError
from tests.evaluation.runners.eval_result_writer import write_eval_multiturn_report
from tests.evaluation.runners.eval_state_closure_rules import (
    check_background_task_followup,
    check_blocked_then_confirm,
    check_common_state_honesty,
    check_continue_without_context,
    check_kb_partial_pending_followup,
    check_material_pending_commit,
    check_save_without_pending,
    check_simple_context_followup,
    check_web_context_followup,
)
from tests.evaluation.runners.eval_state_extractors import (
    extract_commit_state_fields,
    extract_common_state_fields,
    extract_followup_state_fields,
    extract_pending_state_fields,
    extract_session_state_fields,
    extract_task_state_fields,
)


_HARD_CLOSURE_CHECKS = frozenset({
    "save_without_pending",
    "continue_without_context",
    "material_pending_commit",
    "background_task_followup",
    "common_state_honesty",
})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def v2_5_case_file() -> Path:
    return _repo_root() / "tests" / "evaluation" / "cases" / "v2_5_multiturn_state.yaml"


def load_multiturn_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    case_path = Path(path) if path is not None else v2_5_case_file()
    payload = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("v2.5 multiturn case file must be a top-level list")
    return [dict(item) for item in payload]


def _build_payload(flow: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    session_setup = flow.get("session_setup") or {}
    return {
        "message": step["user_input"],
        "session_id": session_setup.get("session_id") or f"eval-{flow['case_id']}",
        "use_knowledge": bool(session_setup.get("use_knowledge", False)),
        "confirm_long_web_video_asr": bool(session_setup.get("confirm_long_web_video_asr", False)),
    }


def _evaluate_expected(step_actual: dict[str, Any], expected: dict[str, Any]) -> tuple[list[str], list[str]]:
    failed_assertions: list[str] = []
    warnings: list[str] = []
    missing_fields = [field for field in ("task_status", "lane") if step_actual.get(field) in (None, "")]
    failed_assertions.extend(f"missing stable field {field}" for field in missing_fields)
    try:
        assert_task_status_is_canonical(step_actual.get("task_status"))
    except ValueError as exc:
        failed_assertions.append(str(exc))
    allowed_map = (
        ("task_status", expected.get("allowed_task_status")),
        ("pending_kind", expected.get("allowed_pending_kinds")),
        ("primary_path", expected.get("allowed_primary_paths")),
        ("mode", expected.get("allowed_modes")),
        ("lane", expected.get("allowed_lanes")),
    )
    for field_name, allowed in allowed_map:
        if allowed:
            try:
                assert_allowed_value(step_actual.get(field_name), allowed, field_name)
            except ValueError as exc:
                failed_assertions.append(str(exc))
    warning_assertions = expected.get("warning_assertions") or {}
    required_trace_fields = (
        warning_assertions.get("required_trace_fields")
        or expected.get("required_trace_fields")
        or []
    )
    if required_trace_fields:
        try:
            assert_required_trace_fields(step_actual.get("extra"), required_trace_fields)
        except ValueError as exc:
            warnings.append(str(exc))
    return failed_assertions, warnings


def _state_for_step(previous_steps: list[dict[str, Any]], response: dict[str, Any]) -> dict[str, Any]:
    actual = {}
    actual.update(extract_common_state_fields(response))
    actual.update(extract_session_state_fields(response))
    actual.update(extract_pending_state_fields(response))
    actual.update(extract_commit_state_fields(response))
    actual.update(extract_task_state_fields(response))
    actual.update(extract_followup_state_fields(previous_steps, response))
    return actual


def evaluate_flow(flow: dict[str, Any], client: EvalHttpClient, *, step_delay_sec: float = 0.0) -> dict[str, Any]:
    flow_steps: list[dict[str, Any]] = []
    flow_failed_assertions: list[str] = []
    flow_warnings: list[str] = []
    session_id = str((flow.get("session_setup") or {}).get("session_id") or f"eval-{flow['case_id']}")

    for raw_step in flow.get("steps") or []:
        step = dict(raw_step)
        payload = _build_payload(flow, step)
        try:
            response = client.post_chat_agno(payload)
        except (BackendUnavailableError, CaseTimeoutError, ExecutionError) as exc:
            error_type = "backend_unavailable" if isinstance(exc, BackendUnavailableError) else "case_timeout" if isinstance(exc, CaseTimeoutError) else "execution_error"
            flow_steps.append(
                {
                    "step_id": step["step_id"],
                    "user_input": step["user_input"],
                    "actual": None,
                    "expected": step.get("expected") or {},
                    "task_status": None,
                    "pending_kind": None,
                    "primary_path": None,
                    "mode": None,
                    "lane": None,
                    "task_id": None,
                    "answer_excerpt": "",
                    "missing_fields": [],
                    "warnings": [],
                    "failed_assertions": [str(exc)],
                    "error_type": error_type,
                }
            )
            flow_failed_assertions.append(str(exc))
            break

        actual = _state_for_step(flow_steps, response)
        failed_assertions, warnings = _evaluate_expected(actual, step.get("expected") or {})
        answer_excerpt = str(actual.get("answer") or "")[:160]
        flow_steps.append(
            {
                "step_id": step["step_id"],
                "user_input": step["user_input"],
                "actual": actual,
                "expected": step.get("expected") or {},
                "task_status": actual.get("task_status"),
                "pending_kind": actual.get("pending_kind"),
                "primary_path": actual.get("primary_path"),
                "mode": actual.get("mode"),
                "lane": actual.get("lane"),
                "task_id": actual.get("task_id"),
                "answer_excerpt": answer_excerpt,
                "missing_fields": [field.replace("missing field ", "") for field in warnings if field.startswith("missing field ")],
                "warnings": warnings,
                "failed_assertions": failed_assertions,
                "error_type": None,
            }
        )
        flow_failed_assertions.extend(failed_assertions)
        flow_warnings.extend(warnings)
        if step_delay_sec > 0:
            time.sleep(step_delay_sec)

    flow_result = {
        "case_id": flow["case_id"],
        "case_name": flow["case_name"],
        "passed": False,
        "session_id": session_id,
        "steps": flow_steps,
        "failed_assertions": flow_failed_assertions,
        "warnings": flow_warnings,
        "error_type": next((step.get("error_type") for step in flow_steps if step.get("error_type")), None),
        "state_markers": {
            "pending_kinds": [step.get("pending_kind") for step in flow_steps],
            "task_statuses": [step.get("task_status") for step in flow_steps],
            "lanes": [step.get("lane") for step in flow_steps],
            "task_ids": [step.get("task_id") for step in flow_steps if step.get("task_id")],
        },
        "closure_checks": [],
    }
    checks = {
        "save_without_pending": check_save_without_pending,
        "continue_without_context": check_continue_without_context,
        "simple_context_followup": check_simple_context_followup,
        "web_context_followup": check_web_context_followup,
        "kb_partial_pending_followup": check_kb_partial_pending_followup,
        "blocked_then_confirm": check_blocked_then_confirm,
        "material_pending_commit": check_material_pending_commit,
        "background_task_followup": check_background_task_followup,
        "common_state_honesty": check_common_state_honesty,
    }
    for name, fn in checks.items():
        if flow["case_id"].startswith(name) or name == "common_state_honesty":
            issues = fn(flow_result)
            flow_result["closure_checks"].append({"name": name, "issues": issues})
            if name in _HARD_CLOSURE_CHECKS:
                flow_result["failed_assertions"].extend(issues)
            else:
                flow_result["warnings"].extend(issues)
    flow_result["passed"] = not flow_result["failed_assertions"]
    return flow_result


def run_multiturn_suite(
    *,
    suite_name: str,
    case_file: str | Path | None = None,
    client: EvalHttpClient | None = None,
    step_delay_sec: float = 0.0,
) -> dict[str, Any]:
    http_client = client or EvalHttpClient()
    started_at = datetime.now().isoformat(timespec="seconds")
    flows = load_multiturn_cases(case_file or v2_5_case_file())
    health = http_client.health_check()
    flow_results = [evaluate_flow(flow, http_client, step_delay_sec=step_delay_sec) for flow in flows]
    finished_at = datetime.now().isoformat(timespec="seconds")
    missing_field_warnings = [
        f"{flow['case_id']}::{step['step_id']}:{field}"
        for flow in flow_results
        for step in flow.get("steps") or []
        for field in step.get("missing_fields") or []
    ]
    fake_state_success_warnings = [
        issue
        for flow in flow_results
        for check in flow.get("closure_checks") or []
        for issue in check.get("issues") or []
        if "fake success" in issue or "fabricated" in issue or "without" in issue
    ]
    report_paths = write_eval_multiturn_report(
        suite_name=suite_name,
        backend_base_url=http_client.base_url,
        started_at=started_at,
        finished_at=finished_at,
        flow_results=flow_results,
        missing_field_warnings=missing_field_warnings,
        fake_state_success_warnings=fake_state_success_warnings,
    )
    return {
        "suite_name": suite_name,
        "health": health,
        "flow_results": flow_results,
        "report_paths": report_paths,
        "backend_base_url": http_client.base_url,
        "started_at": started_at,
        "finished_at": finished_at,
    }
