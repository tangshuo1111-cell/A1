from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.evaluation.runners.eval_rule_catalog import build_rule_coverage_summary
from tests.evaluation.runners.eval_sandbox import ensure_eval_sandbox_dirs


def _timestamp_text(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _report_paths(suite_name: str, timestamp_text: str) -> tuple[Path, Path]:
    reports_dir = ensure_eval_sandbox_dirs()["reports"]
    stem = f"eval_{suite_name}_{timestamp_text}"
    return reports_dir / f"{stem}.json", reports_dir / f"{stem}.md"


def _render_markdown(report: dict[str, Any]) -> str:
    if "regression_suites" in report and "suite_results" in report:
        lines = [
            f"# Eval Report: {report['version_name']}",
            "",
            f"- generated_at: `{report['generated_at']}`",
            f"- backend_status: `{report['backend_status']}`",
            f"- final_verdict: `{report['final_verdict']}`",
            "",
            "## Suite Results",
            "",
            "| suite_name | version_name | status | passed_cases | failed_cases | pass_rate | report_paths |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for suite in report["suite_results"]:
            lines.append(
                f"| {suite['suite_name']} | {suite['version_name']} | {suite['status']} | "
                f"{suite['passed_cases']}/{suite['total_cases']} | {suite['failed_cases']} | {suite['pass_rate']} | "
                f"{suite['report_paths']} |"
            )
        if report.get("known_issue_matches"):
            lines.extend(["", "## Known Issue Matches", ""])
            for item in report["known_issue_matches"]:
                lines.append(f"- {item['suite_name']} / {item['case_id']} -> {item['issue_id']}")
        if report.get("case_timeouts"):
            lines.extend(["", "## Case Timeouts", ""])
            for item in report["case_timeouts"]:
                lines.append(f"- {item['suite_name']} / {item['case_id']}")
        if report.get("execution_errors"):
            lines.extend(["", "## Execution Errors", ""])
            for item in report["execution_errors"]:
                lines.append(f"- {item['suite_name']} / {item['case_id']}")
        if report.get("unknown_failures"):
            lines.extend(["", "## Unknown Failures", ""])
            for item in report["unknown_failures"]:
                lines.append(f"- {item['suite_name']} / {item['case_id']}")
        lines.extend(["", "## Evaluation System Status", ""])
        for key, value in report.get("evaluation_system_status", {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Product Quality Status", ""])
        for key, value in report.get("product_quality_status", {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Governance Rules", ""])
        for key, value in report.get("governance_rules", {}).items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines) + "\n"

    if "agent_collaboration_summary" in report:
        lines = [
            f"# Eval Report: {report['suite_name']}",
            "",
            f"- version_name: `{report.get('version_name', '')}`",
            f"- backend_base_url: `{report['backend_base_url']}`",
            f"- started_at: `{report['started_at']}`",
            f"- finished_at: `{report['finished_at']}`",
            f"- total_cases: `{report['total_cases']}`",
            f"- passed_cases: `{report['passed_cases']}`",
            f"- failed_cases: `{report['failed_cases']}`",
            f"- pass_rate: `{report['pass_rate']}`",
            "",
            "## Case Results",
            "",
            "| case_id | passed | task_status | primary_path | failed_assertions | warnings |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for case in report["case_results"]:
            actual = case.get("actual") or {}
            common = actual.get("common") or {}
            lines.append(
                f"| {case['case_id']} | {case['passed']} | {common.get('task_status')} | {common.get('primary_path')} | "
                f"{'; '.join(case.get('failed_assertions') or []) or '-'} | "
                f"{'; '.join(case.get('warnings') or []) or '-'} |"
            )
        if report.get("missing_field_warnings"):
            lines.extend(["", "## Missing Field Warnings", ""])
            for warning in report["missing_field_warnings"]:
                lines.append(f"- {warning}")
        if report.get("grounding_warnings"):
            lines.extend(["", "## Grounding Warnings", ""])
            for warning in report["grounding_warnings"]:
                lines.append(f"- {warning}")
        if report.get("fake_agent_success_warnings"):
            lines.extend(["", "## Fake Agent Success Warnings", ""])
            for warning in report["fake_agent_success_warnings"]:
                lines.append(f"- {warning}")
        lines.extend(["", "## Agent Collaboration Summary", ""])
        for key, value in report["agent_collaboration_summary"].items():
            lines.append(f"- {key}: {value}")
        if report.get("rule_execution_breakdown"):
            lines.extend(["", "## Rule Execution Breakdown", ""])
            for key, value in report["rule_execution_breakdown"].items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) + "\n"

    if "flow_results" in report:
        lines = [
            f"# Eval Report: {report['suite_name']}",
            "",
            f"- version_name: `{report.get('version_name', '')}`",
            f"- backend_base_url: `{report['backend_base_url']}`",
            f"- started_at: `{report['started_at']}`",
            f"- finished_at: `{report['finished_at']}`",
            f"- total_flows: `{report['total_flows']}`",
            f"- passed_flows: `{report['passed_flows']}`",
            f"- failed_flows: `{report['failed_flows']}`",
            f"- pass_rate: `{report['pass_rate']}`",
            "",
            "## Flow Results",
            "",
            "| case_id | passed | session_id | failed_assertions | warnings |",
            "| --- | --- | --- | --- | --- |",
        ]
        for flow in report["flow_results"]:
            lines.append(
                f"| {flow['case_id']} | {flow['passed']} | {flow['session_id']} | "
                f"{'; '.join(flow.get('failed_assertions') or []) or '-'} | "
                f"{'; '.join(flow.get('warnings') or []) or '-'} |"
            )
        if report.get("missing_field_warnings"):
            lines.extend(["", "## Missing Field Warnings", ""])
            for warning in report["missing_field_warnings"]:
                lines.append(f"- {warning}")
        if report.get("fake_state_success_warnings"):
            lines.extend(["", "## Fake State Success Warnings", ""])
            for warning in report["fake_state_success_warnings"]:
                lines.append(f"- {warning}")
        if report.get("state_closure_summary"):
            lines.extend(["", "## State Closure Summary", ""])
            for key, value in report["state_closure_summary"].items():
                lines.append(f"- {key}: {value}")
        if report.get("rule_execution_breakdown"):
            lines.extend(["", "## Rule Execution Breakdown", ""])
            for key, value in report["rule_execution_breakdown"].items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) + "\n"

    lines = [
        f"# Eval Report: {report['suite_name']}",
        "",
        f"- version_name: `{report.get('version_name', '')}`",
        f"- backend_base_url: `{report['backend_base_url']}`",
        f"- started_at: `{report['started_at']}`",
        f"- finished_at: `{report['finished_at']}`",
        f"- total_cases: `{report['total_cases']}`",
        f"- passed_cases: `{report['passed_cases']}`",
        f"- failed_cases: `{report['failed_cases']}`",
        f"- pass_rate: `{report['pass_rate']}`",
        "",
        "## Case Results",
        "",
        "| case_id | passed | task_status | failed_assertions | warnings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in report["case_results"]:
        actual = case.get("actual") or {}
        lines.append(
            f"| {case['case_id']} | {case['passed']} | {actual.get('task_status')} | "
            f"{'; '.join(case.get('failed_assertions') or []) or '-'} | "
            f"{'; '.join(case.get('warnings') or []) or '-'} |"
        )

    if report.get("fake_success_warnings"):
        lines.extend(["", "## Fake Success Warnings", ""])
        for warning in report["fake_success_warnings"]:
            lines.append(f"- {warning}")

    if report.get("missing_field_warnings"):
        lines.extend(["", "## Missing Field Warnings", ""])
        for warning in report["missing_field_warnings"]:
            lines.append(f"- {warning}")

    if report.get("external_dependency_warnings"):
        lines.extend(["", "## External Dependency Warnings", ""])
        for warning in report["external_dependency_warnings"]:
            lines.append(f"- {warning}")

    if report.get("capability_summary"):
        lines.extend(["", "## Capability Summary", ""])
        for name, summary in report["capability_summary"].items():
            lines.append(
                f"- {name}: total={summary['total']} passed={summary['passed']} "
                f"failed={summary['failed']} fake_success_warnings={summary['fake_success_warnings']}"
            )
    if report.get("failure_breakdown"):
        lines.extend(["", "## Failure Breakdown", ""])
        for name, value in report["failure_breakdown"].items():
            lines.append(f"- {name}: {value}")
    if report.get("warning_breakdown"):
        lines.extend(["", "## Warning Breakdown", ""])
        for name, value in report["warning_breakdown"].items():
            lines.append(f"- {name}: {value}")
    if report.get("rule_execution_breakdown"):
        lines.extend(["", "## Rule Execution Breakdown", ""])
        for name, value in report["rule_execution_breakdown"].items():
            lines.append(f"- {name}: {value}")
    if report.get("rule_coverage_summary"):
        lines.extend(["", "## Rule Coverage Summary", ""])
        for name, value in report["rule_coverage_summary"].items():
            lines.append(f"- {name}: {value}")

    return "\n".join(lines) + "\n"


def _build_capability_summary(case_results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary = {name: {"total": 0, "passed": 0, "failed": 0, "fake_success_warnings": 0} for name in ("web", "document", "video", "kb")}
    for case in case_results:
        category = str((case.get("actual") or {}).get("extra", {}).get("lane") or case.get("case_id", ""))
        source_category = str(case.get("case_id", ""))
        bucket = "web" if source_category.startswith("web_") else "document" if source_category.startswith("document_") else "video" if source_category.startswith("video_") else "kb" if source_category.startswith("kb_") else ""
        if not bucket:
            continue
        summary[bucket]["total"] += 1
        if case.get("passed"):
            summary[bucket]["passed"] += 1
        else:
            summary[bucket]["failed"] += 1
        summary[bucket]["fake_success_warnings"] += sum(1 for warning in case.get("warnings") or [] if "success" in warning)
    return summary


def _classify_failure_type(message: str) -> str:
    text = str(message or "")
    if "missing stable field" in text or "not in allowed values" in text or "not canonical" in text:
        return "stable_contract"
    if "backend_unavailable" in text or "case_timeout" in text or "execution_error" in text:
        return "runtime"
    if any(token in text for token in ("知识库", "网页", "视频", "transcript", "pending", "OCR", "commit")):
        return "evidence_or_state"
    return "other"


def _build_failure_breakdown(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"stable_contract": 0, "evidence_or_state": 0, "runtime": 0, "other": 0}
    for item in results:
        for failure in list(item.get("failed_assertions") or []):
            summary[_classify_failure_type(failure)] += 1
    return summary


def _build_warning_breakdown(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"observability": 0, "wording_or_quality": 0, "fake_success": 0, "other": 0}
    for item in results:
        for warning in list(item.get("warnings") or []):
            text = str(warning or "")
            if "missing" in text or "trace" in text or "observable" in text:
                summary["observability"] += 1
            elif "success" in text or "claimed" in text or "pretend" in text:
                summary["fake_success"] += 1
            elif any(token in text for token in ("warning", "材料", "quality", "ground", "route", "video", "网页", "知识库")):
                summary["wording_or_quality"] += 1
            else:
                summary["other"] += 1
    return summary


def _build_rule_execution_breakdown(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "configured_rules": 0,
        "executed_rules": 0,
        "matched_hard_failures": 0,
        "matched_warnings": 0,
        "missing_checker": 0,
    }
    for item in results:
        for rule in item.get("matched_rule_catalog") or []:
            summary["configured_rules"] += 1
            if rule.get("executed") == "true":
                summary["executed_rules"] += 1
            outcome = str(rule.get("outcome") or "")
            if outcome == "matched_hard_fail":
                summary["matched_hard_failures"] += 1
            elif outcome == "matched_warning":
                summary["matched_warnings"] += 1
            elif outcome == "missing_checker":
                summary["missing_checker"] += 1
    return summary


def write_eval_report(
    *,
    suite_name: str,
    backend_base_url: str,
    started_at: str,
    finished_at: str,
    case_results: list[dict[str, Any]],
    fake_success_warnings: list[str],
    missing_field_warnings: list[str],
    external_dependency_warnings: list[str] | None = None,
    timestamp_text: str | None = None,
) -> dict[str, Path]:
    ts = timestamp_text or _timestamp_text()
    json_path, md_path = _report_paths(suite_name, ts)
    passed_cases = sum(1 for case in case_results if case.get("passed"))
    total_cases = len(case_results)
    failed_cases = total_cases - passed_cases
    pass_rate = round((passed_cases / total_cases) * 100, 2) if total_cases else 0.0

    report = {
        "suite_name": suite_name,
        "version_name": "V2：Capability Chains + Fake Success Negatives" if suite_name.startswith("v2_") else "V1：Route + Exit State + Basic Honesty",
        "backend_base_url": backend_base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "pass_rate": pass_rate,
        "case_results": case_results,
        "capability_summary": _build_capability_summary(case_results),
        "fake_success_warnings": fake_success_warnings,
        "missing_field_warnings": missing_field_warnings,
        "external_dependency_warnings": external_dependency_warnings or [],
        "failure_breakdown": _build_failure_breakdown(case_results),
        "warning_breakdown": _build_warning_breakdown(case_results),
        "rule_execution_breakdown": _build_rule_execution_breakdown(case_results),
        "rule_coverage_summary": build_rule_coverage_summary(),
        "generated_report_paths": {},
    }

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    report["generated_report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def _build_state_closure_summary(flow_results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total_flows": len(flow_results),
        "save_without_pending_checked": 0,
        "continue_without_context_checked": 0,
        "followup_context_checked": 0,
        "blocked_confirm_checked": 0,
        "commit_retrieval_checked": 0,
        "background_task_checked": 0,
        "fake_state_success_warnings_count": 0,
    }
    for flow in flow_results:
        cid = flow.get("case_id", "")
        if cid.startswith("save_without_pending"):
            summary["save_without_pending_checked"] += 1
        if cid.startswith("continue_without_context"):
            summary["continue_without_context_checked"] += 1
        if cid.startswith("simple_context_followup") or cid.startswith("web_context_followup") or cid.startswith("kb_partial_pending_followup"):
            summary["followup_context_checked"] += 1
        if cid.startswith("blocked_then_confirm"):
            summary["blocked_confirm_checked"] += 1
        if cid.startswith("material_pending_commit"):
            summary["commit_retrieval_checked"] += 1
        if cid.startswith("background_task_followup"):
            summary["background_task_checked"] += 1
        summary["fake_state_success_warnings_count"] += sum(
            1 for check in flow.get("closure_checks") or [] for issue in check.get("issues") or [] if "fake" in issue or "fabricated" in issue
        )
    return summary


def write_eval_multiturn_report(
    *,
    suite_name: str,
    backend_base_url: str,
    started_at: str,
    finished_at: str,
    flow_results: list[dict[str, Any]],
    missing_field_warnings: list[str],
    fake_state_success_warnings: list[str],
    timestamp_text: str | None = None,
) -> dict[str, Path]:
    ts = timestamp_text or _timestamp_text()
    json_path, md_path = _report_paths(suite_name, ts)
    passed_flows = sum(1 for flow in flow_results if flow.get("passed"))
    total_flows = len(flow_results)
    failed_flows = total_flows - passed_flows
    pass_rate = round((passed_flows / total_flows) * 100, 2) if total_flows else 0.0
    report = {
        "suite_name": suite_name,
        "version_name": "V2.5：Multi-turn State Closure",
        "backend_base_url": backend_base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_flows": total_flows,
        "passed_flows": passed_flows,
        "failed_flows": failed_flows,
        "pass_rate": pass_rate,
        "flow_results": flow_results,
        "state_closure_summary": _build_state_closure_summary(flow_results),
        "missing_field_warnings": missing_field_warnings,
        "fake_state_success_warnings": fake_state_success_warnings,
        "failure_breakdown": _build_failure_breakdown(flow_results),
        "warning_breakdown": _build_warning_breakdown(flow_results),
        "rule_execution_breakdown": _build_rule_execution_breakdown(flow_results),
        "rule_coverage_summary": build_rule_coverage_summary(),
        "generated_report_paths": {},
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    report["generated_report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def write_eval_agent_report(
    *,
    suite_name: str,
    backend_base_url: str,
    started_at: str,
    finished_at: str,
    case_results: list[dict[str, Any]],
    agent_collaboration_summary: dict[str, int],
    missing_field_warnings: list[str],
    grounding_warnings: list[str],
    fake_agent_success_warnings: list[str],
    timestamp_text: str | None = None,
) -> dict[str, Path]:
    ts = timestamp_text or _timestamp_text()
    json_path, md_path = _report_paths(suite_name, ts)
    passed_cases = sum(1 for case in case_results if case.get("passed"))
    total_cases = len(case_results)
    failed_cases = total_cases - passed_cases
    pass_rate = round((passed_cases / total_cases) * 100, 2) if total_cases else 0.0
    report = {
        "suite_name": suite_name,
        "version_name": "V3：Complex / Agent Collaboration",
        "backend_base_url": backend_base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "pass_rate": pass_rate,
        "case_results": case_results,
        "agent_collaboration_summary": agent_collaboration_summary,
        "missing_field_warnings": missing_field_warnings,
        "grounding_warnings": grounding_warnings,
        "fake_agent_success_warnings": fake_agent_success_warnings,
        "failure_breakdown": _build_failure_breakdown(case_results),
        "warning_breakdown": _build_warning_breakdown(case_results),
        "rule_execution_breakdown": _build_rule_execution_breakdown(case_results),
        "rule_coverage_summary": build_rule_coverage_summary(),
        "generated_report_paths": {},
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    report["generated_report_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def write_regression_overview_report(report: dict[str, Any]) -> dict[str, Path]:
    generated_at = str(report.get("generated_at") or _timestamp_text())
    ts = generated_at.replace("-", "").replace(":", "").replace("T", "_")[:15]
    json_path, md_path = _report_paths("v4_regression_overview", ts)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
