from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

from tests.evaluation.runners.eval_result_writer import write_regression_overview_report


KNOWN_ISSUE_CASE_MAP = {
    "video_total_failure": "KI-V2-001",
    "background_task_followup_flow": "KI-V2.5-001",
    "continue_without_context_flow": "KI-V2.5-002",
    "complex_document_reasoning": "KI-V3-001",
    "complex_interview_explanation": "KI-V3-002",
}


@dataclass(frozen=True)
class KnownIssueRecord:
    issue_id: str
    title: str
    source_version: str
    source_case: str
    status: str


KNOWN_ISSUES = {
    "KI-V2-001": KnownIssueRecord(
        issue_id="KI-V2-001",
        title="video_total_failure 非法视频 URL 被 document_fast succeeded 接管",
        source_version="V2：Capability Chains + Fake Success Negatives",
        source_case="video_total_failure",
        status="Deferred",
    ),
    "KI-V2.5-001": KnownIssueRecord(
        issue_id="KI-V2.5-001",
        title="background_task_followup_flow fake state success",
        source_version="V2.5：Multi-turn State Closure",
        source_case="background_task_followup_flow",
        status="Deferred",
    ),
    "KI-V2.5-002": KnownIssueRecord(
        issue_id="KI-V2.5-002",
        title="continue_without_context_flow 空上下文继续请求被 succeeded + direct_llm 处理",
        source_version="V2.5：Multi-turn State Closure",
        source_case="continue_without_context_flow",
        status="Deferred",
    ),
    "KI-V3-001": KnownIssueRecord(
        issue_id="KI-V3-001",
        title="complex_document_reasoning 内联文档复杂分析协作证据不足",
        source_version="V3：Complex / Agent Collaboration",
        source_case="complex_document_reasoning",
        status="Deferred",
    ),
    "KI-V3-002": KnownIssueRecord(
        issue_id="KI-V3-002",
        title="complex_interview_explanation 退化为 kb_fast",
        source_version="V3：Complex / Agent Collaboration",
        source_case="complex_interview_explanation",
        status="Deferred",
    ),
}

SUITE_VERSION_MAP = {
    "v1_route_exit_state": "V1：Route + Exit State + Basic Honesty",
    "v2_capability_all": "V2：Capability Chains + Fake Success Negatives",
    "v2_5_multiturn_state": "V2.5：Multi-turn State Closure",
    "v3_complex_agent": "V3：Complex / Agent Collaboration",
}


def _iter_failed_ids(suite_result: dict[str, Any]) -> list[str]:
    if "flow_results" in suite_result:
        return [item.get("case_id", "") for item in suite_result.get("flow_results") or [] if not item.get("passed")]
    return [item.get("case_id", "") for item in suite_result.get("case_results") or [] if not item.get("passed")]


def _iter_failed_items(suite_result: dict[str, Any]) -> list[dict[str, Any]]:
    if "flow_results" in suite_result:
        return [item for item in suite_result.get("flow_results") or [] if not item.get("passed")]
    return [item for item in suite_result.get("case_results") or [] if not item.get("passed")]


def classify_suite_result(suite_result: dict[str, Any]) -> dict[str, Any]:
    suite_name = str(suite_result.get("suite_name") or "")
    backend_unavailable = bool(suite_result.get("backend_unavailable"))
    failed_items = _iter_failed_items(suite_result)
    failed_ids = [str(item.get("case_id") or "") for item in failed_items]
    known_matches = []
    unknown_failures = []
    case_timeouts = []
    execution_errors = []
    for case_id in failed_ids:
        issue_id = KNOWN_ISSUE_CASE_MAP.get(case_id)
        if issue_id:
            known_matches.append({"case_id": case_id, "issue_id": issue_id})
        else:
            unknown_failures.append(case_id)
    for item in failed_items:
        case_id = str(item.get("case_id") or "")
        error_type = str(item.get("error_type") or "")
        if error_type == "case_timeout":
            case_timeouts.append(case_id)
        elif error_type == "execution_error":
            execution_errors.append(case_id)
        elif error_type == "backend_unavailable":
            backend_unavailable = True

    unknown_failures = [case_id for case_id in unknown_failures if case_id not in case_timeouts and case_id not in execution_errors]

    if backend_unavailable:
        status = "backend_unavailable"
    elif case_timeouts:
        status = "case_timeout"
    elif execution_errors:
        status = "execution_error"
    elif unknown_failures:
        status = "failed_unknown"
    elif known_matches:
        status = "failed_known_issue"
    else:
        status = "passed"

    total = suite_result.get("total_cases")
    passed = suite_result.get("passed_cases")
    failed = suite_result.get("failed_cases")
    if total is None:
        total = suite_result.get("total_flows", 0)
        passed = suite_result.get("passed_flows", 0)
        failed = suite_result.get("failed_flows", 0)
    report_paths = {
        key: str(value)
        for key, value in (suite_result.get("report_paths") or {}).items()
    }
    return {
        "suite_name": suite_name,
        "version_name": SUITE_VERSION_MAP.get(suite_name, suite_name),
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "pass_rate": suite_result.get("pass_rate", 0.0),
        "status": status,
        "report_paths": report_paths,
        "known_issue_matches": known_matches,
        "unknown_failures": unknown_failures,
        "case_timeouts": case_timeouts,
        "execution_errors": execution_errors,
    }


def build_regression_overview(
    regression_results: list[dict[str, Any]],
    *,
    backend_status: str,
) -> dict[str, Any]:
    suite_results = [classify_suite_result(item) for item in regression_results]
    known_issue_matches = [
        {"suite_name": suite["suite_name"], **match}
        for suite in suite_results
        for match in suite["known_issue_matches"]
    ]
    unknown_failures = [
        {"suite_name": suite["suite_name"], "case_id": case_id}
        for suite in suite_results
        for case_id in suite["unknown_failures"]
    ]
    case_timeouts = [
        {"suite_name": suite["suite_name"], "case_id": case_id}
        for suite in suite_results
        for case_id in suite["case_timeouts"]
    ]
    execution_errors = [
        {"suite_name": suite["suite_name"], "case_id": case_id}
        for suite in suite_results
        for case_id in suite["execution_errors"]
    ]
    known_issues = [
        {
            "issue_id": item.issue_id,
            "title": item.title,
            "source_version": item.source_version,
            "source_case": item.source_case,
            "status": item.status,
        }
        for item in KNOWN_ISSUES.values()
    ]
    product_quality_status = {
        "has_known_issues": True,
        "has_unknown_failures": bool(unknown_failures),
        "recommended_next_step": "进入已知问题治理阶段" if not unknown_failures else "先人工判断 unknown failures",
    }
    evaluation_system_status = {
        "V0": "已完成",
        "V1": "已完成",
        "V2": "已完成",
        "V2.5": "评测体系已完成",
        "V3": "评测体系已完成",
        "V4": "当前总览已生成",
    }
    final_verdict = "V4：Report + Regression Gate 已完成" if backend_status in {"ok", "degraded"} else "V4：Report + Regression Gate 未完成"
    return {
        "version_name": "V4：Report + Regression Gate",
        "generated_at": "",
        "regression_suites": [item["suite_name"] for item in suite_results],
        "suite_results": suite_results,
        "known_issues": known_issues,
        "known_issue_matches": known_issue_matches,
        "unknown_failures": unknown_failures,
        "case_timeouts": case_timeouts,
        "execution_errors": execution_errors,
        "backend_status": backend_status,
        "evaluation_system_status": evaluation_system_status,
        "product_quality_status": product_quality_status,
        "governance_rules": {
            "pm_doc": "PM 文档只写摘要",
            "known_issues": "known_issues.md 记录真实缺陷",
            "reports": "reports 保留原始证据",
            "execution_classification": "case_timeout / execution_error 与产品失败分开记录",
        },
        "final_verdict": final_verdict,
    }


def render_regression_overview(
    *,
    regression_results: list[dict[str, Any]],
    backend_status: str,
    generated_at: str,
) -> dict[str, Path]:
    report = build_regression_overview(regression_results, backend_status=backend_status)
    report["generated_at"] = generated_at
    return write_regression_overview_report(report)


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
