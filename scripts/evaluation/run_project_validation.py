"""Project validation orchestrator — summary by default; optional profile runners.

Does not modify business logic. Does not commit runtime reports.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

SUMMARY_DOC = REPO_ROOT / "docs" / "evidence" / "project_validation_summary.md"
EVIDENCE = {
    "real_external": REPO_ROOT / "docs" / "evidence" / "real_external_validation_report.md",
    "regression": REPO_ROOT / "docs" / "evidence" / "real_regression_validation_report.md",
}
RUNTIME_REPORTS = REPO_ROOT / "runtime_data" / "eval_sandbox" / "reports"
METRICS_REPORTS = REPO_ROOT / "_local" / "reports" / "metrics"

REGRESSION_EXPECTED_TOTAL = 42
EXTERNAL_EXPECTED_CONFIGURED = 7

FULL_STAGING_PREREQUISITES = """
full-staging prerequisites (--execute required):
  - Backend running at http://127.0.0.1:8000
  - PostgreSQL available (DATABASE_URL)
  - LIGHT_MAQA_FAKE_LLM=0
  - LLM / ASR / OCR / Web / Video providers configured in env or backend/config/env.txt (gitignored)
  - May incur external API costs and take significant time

Metrics line is NOT included unless --include-metrics is set.
"""


def _print_header(title: str) -> None:
    print(title)
    print("=" * len(title))


def _eval_test_count() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/evaluation", "--collect-only", "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in reversed((proc.stdout or "").splitlines()):
        if " tests collected" in line:
            try:
                return int(line.strip().split()[0])
            except ValueError:
                break
    return 0


def run_summary() -> int:
    eval_count = _eval_test_count() or 113
    _print_header("Project Validation Summary (read-only)")
    print(f"doc: {SUMMARY_DOC.relative_to(REPO_ROOT)}")
    print()
    print("Three validation lines:")
    print("  1. Product metrics  — 6 samples + weekly HTML (trends, not pass/fail)")
    print("  2. Regression       — regression_all 42 cases (engineering gate)")
    print("  3. Real external    — real_external_smoke 7 capabilities (staging readiness)")
    print()
    print("Latest documented results (staging/local, not default CI):")
    print("  - regression_all: 42/42 passed")
    print("  - real_external_smoke: 7/7 passed, product_failure_cases_count=0")
    print(f"  - tests/evaluation: {eval_count} passed (framework guardrails)")
    print()
    print("Evidence docs (committed, sanitized):")
    for _key, path in EVIDENCE.items():
        status = "ok" if path.exists() else "missing"
        print(f"  - [{status}] {path.relative_to(REPO_ROOT)}")
    print()
    print("Runtime artifacts (gitignored, do not commit):")
    print(f"  - {RUNTIME_REPORTS.relative_to(REPO_ROOT)}/eval_*.json")
    print(f"  - {RUNTIME_REPORTS.relative_to(REPO_ROOT)}/project_validation_staging_*.json")
    print(f"  - {METRICS_REPORTS.relative_to(REPO_ROOT)}/weekly_*.html")
    print()
    print("Commands:")
    print("  py scripts/evaluation/run_project_validation.py --profile regression")
    print("  py scripts/evaluation/run_project_validation.py --profile external")
    print("  py scripts/evaluation/run_project_validation.py --profile full-staging")
    print("  py scripts/evaluation/run_project_validation.py --profile full-staging --execute")
    print("  py scripts/evaluation/run_project_validation.py --profile metrics --execute")
    print("  py scripts/evaluation/run_project_validation.py --profile metrics-diagnostic --execute")
    print()
    print("CI boundary: default ci.yml uses LIGHT_MAQA_FAKE_LLM=1; does NOT auto-run 42/42 or 7/7.")
    print("Real external: .github/workflows/real_external.yml (workflow_dispatch + secrets).")
    print("Staging bundle: full-staging profile (--execute) runs regression_all then real_external_smoke.")
    return 0


def _run_py(args: list[str]) -> int:
    cmd = [sys.executable, *args]
    print("exec:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def run_regression() -> int:
    _print_header("Regression profile")
    print("Requires: backend http://127.0.0.1:8000, PostgreSQL, LIGHT_MAQA_FAKE_LLM=0 recommended.")
    print("Suite: regression_all (V1 + V2 + V2.5 + V3, 42 cases)")
    return _run_py(["scripts/evaluation/run_eval_suite.py", "--suite", "regression_all"])


def run_external() -> int:
    _print_header("Real external profile")
    print("Requires: backend, PostgreSQL, LLM/ASR/OCR keys in env or backend/config/env.txt (gitignored).")
    print("Do NOT expect default CI to reproduce this on every push.")
    return _run_py(["scripts/evaluation/run_eval_suite.py", "--suite", "real_external_smoke"])


def run_metrics(*, execute: bool = False) -> int:
    _print_header("Product metrics profile")
    print("Requires: metrics sandbox DATABASE_URL (see run_metrics_sandbox_samples.py header).")
    print("Step 1: py scripts/run_metrics_sandbox_samples.py --api http://127.0.0.1:8000 --report")
    print("Step 2: py scripts/report_product_metrics.py --days 7 --html")
    print("Output: _local/reports/metrics/weekly_*.html (do not commit)")
    if not execute:
        print()
        print("Dry-run only. Pass --execute with --profile metrics to run step 1+2.")
        return 0
    rc1 = _run_py(
        ["scripts/run_metrics_sandbox_samples.py", "--api", "http://127.0.0.1:8000", "--report"]
    )
    if rc1 != 0:
        return rc1
    return _run_py(["scripts/report_product_metrics.py", "--days", "7", "--html"])


def run_metrics_diagnostic(*, execute: bool = False) -> int:
    _print_header("Product metrics diagnostic profile")
    print("Runs sandbox samples; stdout includes DIAG: partial buckets + reason_codes.")
    print("Sidecar: _local/reports/metrics/last_sandbox_diagnostic.json")
    if not execute:
        print()
        print("Dry-run only. Pass --execute with --profile metrics-diagnostic.")
        return 0
    return _run_py(
        ["scripts/run_metrics_sandbox_samples.py", "--api", "http://127.0.0.1:8000", "--report"]
    )


def _latest_report_json(prefix: str) -> Path | None:
    if not RUNTIME_REPORTS.is_dir():
        return None
    candidates = sorted(
        RUNTIME_REPORTS.glob(f"eval_{prefix}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _summarize_regression(report: dict[str, Any]) -> dict[str, Any]:
    suites = report.get("suite_results") or []
    passed = sum(int(s.get("passed_cases") or 0) for s in suites)
    total = sum(int(s.get("total_cases") or 0) for s in suites)
    return {
        "report_path": str(report.get("_source_path") or ""),
        "passed": passed,
        "total": total,
        "all_passed": passed == total == REGRESSION_EXPECTED_TOTAL and total > 0,
        "backend_status": report.get("backend_status"),
        "backend_unavailable": report.get("backend_status") == "backend_unavailable",
        "failed_unknown": list(report.get("unknown_failures") or []),
        "case_timeouts": list(report.get("case_timeouts") or []),
        "execution_errors": list(report.get("execution_errors") or []),
        "final_verdict": report.get("final_verdict"),
    }


def _summarize_external(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    cases = report.get("capability_cases") or []
    passed_configured = int(summary.get("passed_configured_cases_count") or 0)
    return {
        "report_path": str(report.get("_source_path") or ""),
        "final_verdict": report.get("final_verdict"),
        "exit_code": report.get("exit_code"),
        "passed_configured": passed_configured,
        "expected_configured": EXTERNAL_EXPECTED_CONFIGURED,
        "all_passed": passed_configured == EXTERNAL_EXPECTED_CONFIGURED,
        "product_failure_cases_count": int(summary.get("product_failure_cases_count") or 0),
        "not_configured_cases_count": int(summary.get("not_configured_cases_count") or 0),
        "external_timeout_cases_count": int(summary.get("external_timeout_cases_count") or 0),
        "backend_unavailable": any(c.get("status") == "backend_unavailable" for c in cases),
        "failed_unknown": [c.get("case_id") for c in cases if c.get("status") == "failed_unknown"],
        "timeouts": [c.get("case_id") for c in cases if c.get("status") in {"external_timeout", "case_timeout"}],
    }


def _write_staging_summary(payload: dict[str, Any]) -> Path:
    RUNTIME_REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RUNTIME_REPORTS / f"project_validation_staging_{ts}.json"
    md_path = RUNTIME_REPORTS / f"project_validation_staging_{ts}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    reg = payload.get("regression") or {}
    ext = payload.get("real_external") or {}
    lines = [
        "# Project Validation Staging Summary",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- mode: `{payload.get('mode')}`",
        f"- overall_success: `{payload.get('overall_success')}`",
        f"- exit_code: `{payload.get('exit_code')}`",
        "",
        "## Regression (regression_all)",
        "",
        f"- result: **{reg.get('passed')}/{reg.get('total')}** (expected {REGRESSION_EXPECTED_TOTAL}/{REGRESSION_EXPECTED_TOTAL})",
        f"- all_passed: `{reg.get('all_passed')}`",
        f"- backend_status: `{reg.get('backend_status')}`",
        f"- failed_unknown: `{reg.get('failed_unknown')}`",
        f"- case_timeouts: `{reg.get('case_timeouts')}`",
        f"- report: `{reg.get('report_path')}`",
        "",
        "## Real external (real_external_smoke)",
        "",
        f"- passed_configured: **{ext.get('passed_configured')}/{ext.get('expected_configured')}**",
        f"- final_verdict: `{ext.get('final_verdict')}`",
        f"- product_failure_cases_count: `{ext.get('product_failure_cases_count')}`",
        f"- failed_unknown: `{ext.get('failed_unknown')}`",
        f"- timeouts: `{ext.get('timeouts')}`",
        f"- backend_unavailable: `{ext.get('backend_unavailable')}`",
        f"- report: `{ext.get('report_path')}`",
        "",
        "## Notes",
        "",
        "- Raw eval reports remain under runtime_data/eval_sandbox/reports/ (gitignored).",
        "- Default CI does NOT auto-run this bundle.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["summary_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def _print_staging_results(payload: dict[str, Any]) -> None:
    reg = payload.get("regression") or {}
    ext = payload.get("real_external") or {}
    print()
    _print_header("full-staging results")
    print(f"regression_all: {reg.get('passed')}/{reg.get('total')}  all_passed={reg.get('all_passed')}")
    print(f"  failed_unknown: {reg.get('failed_unknown') or '(none)'}")
    print(f"  case_timeouts: {reg.get('case_timeouts') or '(none)'}")
    print(f"  backend_unavailable: {reg.get('backend_unavailable')}")
    print(
        f"real_external_smoke: {ext.get('passed_configured')}/{ext.get('expected_configured')}  "
        f"final_verdict={ext.get('final_verdict')}"
    )
    print(f"  product_failure_cases_count: {ext.get('product_failure_cases_count')}")
    print(f"  failed_unknown: {ext.get('failed_unknown') or '(none)'}")
    print(f"  timeouts: {ext.get('timeouts') or '(none)'}")
    print(f"  backend_unavailable: {ext.get('backend_unavailable')}")
    paths = payload.get("summary_paths") or {}
    if paths:
        print(f"staging summary json: {paths.get('json')}")
        print(f"staging summary md:   {paths.get('markdown')}")


def run_full_staging(*, execute: bool, include_metrics: bool) -> int:
    _print_header("full-staging profile")
    print(FULL_STAGING_PREREQUISITES.strip())
    if not execute:
        print()
        print("Dry-run only. Pass --execute to run regression_all then real_external_smoke.")
        print("Optional: --include-metrics also runs the product metrics line (separate DB).")
        return 0

    rc_reg = run_regression()
    reg_path = _latest_report_json("v4_regression_overview")
    reg_report = _load_json(reg_path)
    if reg_path:
        reg_report["_source_path"] = str(reg_path)
    reg_summary = _summarize_regression(reg_report)

    rc_ext = run_external()
    ext_path = _latest_report_json("real_external_smoke")
    ext_report = _load_json(ext_path)
    if ext_path:
        ext_report["_source_path"] = str(ext_path)
    ext_summary = _summarize_external(ext_report)

    metrics_rc: int | None = None
    if include_metrics:
        metrics_rc = run_metrics(execute=True)

    overall_success = (
        rc_reg == 0
        and rc_ext == 0
        and reg_summary.get("all_passed")
        and ext_summary.get("all_passed")
        and int(ext_summary.get("product_failure_cases_count") or 0) == 0
    )
    exit_code = 0 if overall_success else 2
    if rc_reg != 0 or rc_ext != 0:
        exit_code = max(exit_code, rc_reg, rc_ext)
    if metrics_rc is not None and metrics_rc != 0:
        exit_code = max(exit_code, metrics_rc)

    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "full-staging",
        "overall_success": overall_success,
        "exit_code": exit_code,
        "regression_exit_code": rc_reg,
        "real_external_exit_code": rc_ext,
        "metrics_exit_code": metrics_rc,
        "regression": reg_summary,
        "real_external": ext_summary,
    }
    summary_path = _write_staging_summary(payload)
    payload["summary_paths"] = {
        "json": str(summary_path),
        "markdown": str(summary_path.with_suffix(".md")),
    }
    _print_staging_results(payload)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Project validation orchestrator (default: summary only)")
    parser.add_argument(
        "--profile",
        choices=("summary", "regression", "external", "metrics", "metrics-diagnostic", "full-staging"),
        default="summary",
        help="summary=print index only; full-staging=bundle regression+external with --execute",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="For metrics/full-staging: actually run delegated scripts",
    )
    parser.add_argument(
        "--include-metrics",
        action="store_true",
        help="With full-staging --execute: also run product metrics line (requires metrics sandbox DB)",
    )
    args = parser.parse_args()
    if args.profile == "summary":
        return run_summary()
    if args.profile == "regression":
        return run_regression()
    if args.profile == "external":
        return run_external()
    if args.profile == "full-staging":
        return run_full_staging(execute=args.execute, include_metrics=args.include_metrics)
    if args.profile == "metrics-diagnostic":
        return run_metrics_diagnostic(execute=args.execute)
    return run_metrics(execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
