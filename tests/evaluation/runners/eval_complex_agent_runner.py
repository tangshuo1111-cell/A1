from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from tests.evaluation.runners.eval_agent_collaboration_rules import (
    check_answer_grounded_in_material,
    check_common_agent_collaboration,
    check_evidence_insufficiency_honesty,
    check_main_plan_observable,
    check_middle_material_observable,
    check_multi_source_alignment,
    check_quality_gate_honesty,
    check_second_round_observability,
    check_video_material_honesty,
)
from tests.evaluation.runners.eval_agent_extractors import (
    extract_agent_common_fields,
    extract_answer_grounding_fields,
    extract_main_plan_fields,
    extract_middle_material_fields,
    extract_quality_gate_fields,
    extract_second_round_fields,
)
from tests.evaluation.runners.eval_assertions import (
    assert_allowed_value,
    assert_task_status_is_canonical,
)
from tests.evaluation.runners.eval_field_catalog import classify_field
from tests.evaluation.runners.eval_http_client import (
    BackendUnavailableError,
    CaseTimeoutError,
    EvalHttpClient,
    ExecutionError,
)
from tests.evaluation.runners.eval_result_writer import write_eval_agent_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def v3_case_file() -> Path:
    return _repo_root() / "tests" / "evaluation" / "cases" / "v3_complex_agent.yaml"


def load_v3_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    case_path = Path(path) if path is not None else v3_case_file()
    payload = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("v3 complex agent case file must be a top-level list")
    return [dict(item) for item in payload]


def _build_payload(case: dict[str, Any]) -> dict[str, Any]:
    session_setup = case.get("session_setup") or {}
    payload = {
        "message": case["user_input"],
        "session_id": session_setup.get("session_id") or f"eval-{case['case_id']}",
        "use_knowledge": bool(session_setup.get("use_knowledge", False)),
    }
    if "confirm_long_web_video_asr" in session_setup:
        payload["confirm_long_web_video_asr"] = bool(session_setup.get("confirm_long_web_video_asr"))
    return payload


def _evaluate_hard_assertions(case: dict[str, Any], common: dict[str, Any], aggregate_actual: dict[str, Any]) -> tuple[list[str], list[str]]:
    expected = (case.get("expected") or {}).get("hard_assertions") or {}
    warning_assertions = (case.get("expected") or {}).get("warning_assertions") or {}
    failures: list[str] = []
    warnings: list[str] = []

    try:
        assert_task_status_is_canonical(common.get("task_status"))
    except ValueError as exc:
        failures.append(str(exc))

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
                assert_allowed_value(common.get(field_name), allowed, field_name)
            except ValueError as exc:
                failures.append(str(exc))

    must_have_one_of = list(expected.get("must_have_one_of") or [])
    if must_have_one_of:
        stable_keys = [
            key
            for key in must_have_one_of
            if classify_field(key).tier in {"stable_contract", "stable_result", "contextual"}
        ]
        fragile_keys = [
            key
            for key in must_have_one_of
            if classify_field(key).tier == "fragile_observability"
        ]
        found = False
        for key in stable_keys:
            if "." in key:
                head, tail = key.split(".", 1)
                value = ((aggregate_actual.get(head) or {}) if isinstance(aggregate_actual.get(head), dict) else {}).get(tail)
            else:
                value = common.get(key)
                if value in (None, "", [], {}, ()) and key in aggregate_actual:
                    value = aggregate_actual.get(key)
            if value not in (None, "", [], {}, ()):
                found = True
                break
        if stable_keys and not found:
            failures.append(f"none of stable must_have_one_of fields observable: {', '.join(stable_keys)}")
        if fragile_keys:
            warnings.append(
                "fragile must_have_one_of fields tracked as observability only: "
                + ", ".join(fragile_keys)
            )

    required_trace_fields = list(warning_assertions.get("required_trace_fields") or [])
    if required_trace_fields:
        warnings.append(
            "warning_assertions.required_trace_fields configured: "
            + ", ".join(required_trace_fields)
        )
    return failures, warnings


def _extract_actual(response: dict[str, Any]) -> dict[str, Any]:
    common = extract_agent_common_fields(response)
    plan = extract_main_plan_fields(response)
    material = extract_middle_material_fields(response)
    grounding = extract_answer_grounding_fields(response)
    quality = extract_quality_gate_fields(response)
    second_round = extract_second_round_fields(response)
    return {
        "common": common,
        "plan": plan,
        "material": material,
        "grounding": grounding,
        "quality": quality,
        "second_round": second_round,
        "answer": grounding.get("answer"),
        "task_status": common.get("task_status"),
        "primary_path": common.get("primary_path"),
        "mode": common.get("mode"),
        "lane": common.get("lane"),
        "pending_kind": common.get("pending_kind"),
    }


def evaluate_v3_case(case: dict[str, Any], client: EvalHttpClient) -> dict[str, Any]:
    try:
        response = client.post_chat_agno(_build_payload(case))
    except (BackendUnavailableError, CaseTimeoutError, ExecutionError) as exc:
        error_type = "backend_unavailable" if isinstance(exc, BackendUnavailableError) else "case_timeout" if isinstance(exc, CaseTimeoutError) else "execution_error"
        return {
            "case_id": case["case_id"],
            "case_name": case["case_name"],
            "passed": False,
            "actual": None,
            "expected": case.get("expected") or {},
            "failed_assertions": [str(exc)],
            "warnings": [],
            "missing_fields": [],
            "error_type": error_type,
            "agent_markers": {},
            "plan_markers": {},
            "material_markers": {},
            "grounding_markers": {},
            "quality_gate_markers": {},
            "second_round_markers": {},
        }

    actual = _extract_actual(response)
    common = actual["common"]
    failures, warnings = _evaluate_hard_assertions(case, common, actual)

    soft_fields = list(
        ((case.get("expected") or {}).get("soft_observability") or {}).get("try_extract") or []
    )
    missing_fields: list[str] = []
    for field_name in soft_fields:
        value = None
        if "." in field_name:
            head, tail = field_name.split(".", 1)
            bucket = actual.get("quality") if head == "quality_gate" else actual.get(head)
            if isinstance(bucket, dict):
                value = bucket.get(tail)
        else:
            for bucket_name in ("plan", "material", "grounding", "quality", "second_round", "common"):
                bucket = actual.get(bucket_name) or {}
                if isinstance(bucket, dict) and field_name in bucket:
                    value = bucket.get(field_name)
                    break
        if value in (None, "", [], {}, ()):
            missing_fields.append(field_name)

    rule_sets = [
        check_common_agent_collaboration(case, actual),
        check_answer_grounded_in_material(case, actual),
        check_evidence_insufficiency_honesty(case, actual),
        check_multi_source_alignment(case, actual),
        check_video_material_honesty(case, actual),
    ]
    warning_rule_sets = [
        check_main_plan_observable(case, actual),
        check_middle_material_observable(case, actual),
        check_quality_gate_honesty(case, actual),
        check_second_round_observability(case, actual),
    ]
    for issues in rule_sets:
        failures.extend(issues)
    for issues in warning_rule_sets:
        warnings.extend(issues)
    warnings.extend(f"missing soft field {field}" for field in missing_fields)

    return {
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "passed": not failures,
        "actual": actual,
        "expected": case.get("expected") or {},
        "failed_assertions": failures,
        "warnings": warnings,
        "missing_fields": missing_fields,
        "error_type": None,
        "agent_markers": {
            "task_status": common.get("task_status"),
            "primary_path": common.get("primary_path"),
            "lane": common.get("lane"),
            "mode": common.get("mode"),
        },
        "plan_markers": actual["plan"],
        "material_markers": actual["material"],
        "grounding_markers": actual["grounding"],
        "quality_gate_markers": actual["quality"],
        "second_round_markers": actual["second_round"],
    }


def _build_agent_collaboration_summary(case_results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total_cases": len(case_results),
        "main_plan_observable_count": 0,
        "middle_material_observable_count": 0,
        "answer_grounding_observable_count": 0,
        "quality_gate_observable_count": 0,
        "insufficient_evidence_honesty_count": 0,
        "multi_source_alignment_checked_count": 0,
        "video_honesty_checked_count": 0,
        "second_round_observable_count": 0,
        "fake_agent_success_warnings_count": 0,
        "missing_field_warnings_count": 0,
    }
    for case in case_results:
        actual = case.get("actual") or {}
        if (actual.get("plan") or {}).get("route_decision") not in (None, "") or (actual.get("plan") or {}).get("v6_main_pan_renwu") not in (None, ""):
            summary["main_plan_observable_count"] += 1
        if (actual.get("material") or {}).get("material_sufficiency") not in (None, "") or (actual.get("material") or {}).get("v6_middle_pan_laiyuan") not in (None, ""):
            summary["middle_material_observable_count"] += 1
        if (actual.get("grounding") or {}).get("answer"):
            summary["answer_grounding_observable_count"] += 1
        if (actual.get("quality") or {}).get("quality_gate") not in (None, {}):
            summary["quality_gate_observable_count"] += 1
        if any("evidence insufficiency" in item or "absolute conclusion" in item for item in case.get("failed_assertions") or []):
            pass
        else:
            summary["insufficient_evidence_honesty_count"] += 1
        if "multi_source" in str((actual.get("common") or {}).get("primary_path", "")) or "multi_source" in str(case.get("case_id", "")) or "complex_multi_source" in str(case.get("case_name", "")):
            summary["multi_source_alignment_checked_count"] += 1
        if "video" in str(case.get("case_id", "")):
            summary["video_honesty_checked_count"] += 1
        if (actual.get("second_round") or {}).get("need_second_round") not in (None, "") or (actual.get("second_round") or {}).get("feedback_gate_result") not in (None, {}):
            summary["second_round_observable_count"] += 1
        summary["fake_agent_success_warnings_count"] += sum(1 for item in (case.get("failed_assertions") or []) if "claimed" in item or "strong conclusion" in item)
        summary["missing_field_warnings_count"] += len(case.get("missing_fields") or [])
    return summary


def run_v3_suite(
    *,
    suite_name: str,
    case_file: str | Path | None = None,
    client: EvalHttpClient | None = None,
) -> dict[str, Any]:
    http_client = client or EvalHttpClient()
    started_at = datetime.now().isoformat(timespec="seconds")
    health = http_client.health_check()
    cases = load_v3_cases(case_file or v3_case_file())
    case_results = [evaluate_v3_case(case, http_client) for case in cases]
    finished_at = datetime.now().isoformat(timespec="seconds")
    missing_field_warnings = [
        f"{case['case_id']}:{field}"
        for case in case_results
        for field in case.get("missing_fields") or []
    ]
    grounding_warnings = [
        issue
        for case in case_results
        for issue in case.get("warnings") or []
        if "ground" in issue or "material" in issue or "quality gate" in issue
    ]
    fake_agent_success_warnings = [
        issue
        for case in case_results
        for issue in (case.get("failed_assertions") or []) + (case.get("warnings") or [])
        if "claimed" in issue or "strong conclusion" in issue or "pretend" in issue
    ]
    report_paths = write_eval_agent_report(
        suite_name=suite_name,
        backend_base_url=http_client.base_url,
        started_at=started_at,
        finished_at=finished_at,
        case_results=case_results,
        agent_collaboration_summary=_build_agent_collaboration_summary(case_results),
        missing_field_warnings=missing_field_warnings,
        grounding_warnings=grounding_warnings,
        fake_agent_success_warnings=fake_agent_success_warnings,
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
