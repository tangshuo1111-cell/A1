"""Project validation orchestrator — summary by default; optional profile runners.

Does not modify business logic. Does not commit runtime reports.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SUMMARY_DOC = REPO_ROOT / "docs" / "evidence" / "project_validation_summary.md"
EVIDENCE = {
    "real_external": REPO_ROOT / "docs" / "evidence" / "real_external_validation_report.md",
    "regression": REPO_ROOT / "docs" / "evidence" / "real_regression_validation_report.md",
}
RUNTIME_REPORTS = REPO_ROOT / "runtime_data" / "eval_sandbox" / "reports"
METRICS_REPORTS = REPO_ROOT / "_local" / "reports" / "metrics"


def _print_header(title: str) -> None:
    print(title)
    print("=" * len(title))


def run_summary() -> int:
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
    print("  - tests/evaluation: 112 passed (framework guardrails)")
    print()
    print("Evidence docs (committed, sanitized):")
    for key, path in EVIDENCE.items():
        status = "ok" if path.exists() else "missing"
        print(f"  - [{status}] {path.relative_to(REPO_ROOT)}")
    print()
    print("Runtime artifacts (gitignored, do not commit):")
    print(f"  - {RUNTIME_REPORTS.relative_to(REPO_ROOT)}/eval_*.json")
    print(f"  - {METRICS_REPORTS.relative_to(REPO_ROOT)}/weekly_*.html")
    print()
    print("Commands:")
    print("  py scripts/evaluation/run_project_validation.py --profile regression")
    print("  py scripts/evaluation/run_project_validation.py --profile external")
    print("  py scripts/evaluation/run_project_validation.py --profile metrics")
    print()
    print("CI boundary: default ci.yml uses LIGHT_MAQA_FAKE_LLM=1; does NOT auto-run 42/42 or 7/7.")
    print("Real external: .github/workflows/real_external.yml (workflow_dispatch + secrets).")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Project validation orchestrator (default: summary only)")
    parser.add_argument(
        "--profile",
        choices=("summary", "regression", "external", "metrics"),
        default="summary",
        help="summary=print index only; others delegate to existing scripts",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="For metrics profile only: actually run sandbox samples + weekly report",
    )
    args = parser.parse_args()
    if args.profile == "summary":
        return run_summary()
    if args.profile == "regression":
        return run_regression()
    if args.profile == "external":
        return run_external()
    return run_metrics(execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
