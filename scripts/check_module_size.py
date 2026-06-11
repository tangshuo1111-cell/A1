#!/usr/bin/env python3
"""Module line-count guard (Round 13) — prevent growth on watched chat modules.

Baseline: tests/migration/module_size_baseline.json (current snapshot; must not grow)
Targets: aspirational limits from the 15-round plan (informational until R15 convergence)

Usage:
    python scripts/check_module_size.py [--baseline PATH] [--strict-targets]
                                        [--metric all|code] [--report-dual]

Exit codes:
    0  All watched modules within baseline (and targets if --strict-targets).
    1  One or more modules exceed baseline or target limits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "tests" / "migration" / "module_size_baseline.json"

# Aspirational end-state limits (Round 13 plan); files above these warn until R15.
TARGET_LIMITS: dict[str, int] = {
    "backend/application/chat/run_chat_turn.py": 60,
    "backend/application/chat/turn_orchestrator.py": 90,
    "backend/application/chat/turn_state_machine.py": 380,
    "backend/application/chat/turn_response_builder.py": 280,
    "backend/application/chat/executors/async_executor.py": 320,
    "backend/application/chat/executors/complex_executor.py": 60,
    "backend/application/chat/executors/complex_executor_delivery.py": 200,
    "backend/application/chat/executors/complex_executor_exit_extra.py": 150,
    "backend/application/chat/executors/complex_executor_main_stage.py": 100,
    "backend/application/chat/executors/complex_executor_middle_stage.py": 100,
    "backend/application/chat/executors/complex_executor_answer_stage.py": 150,
    "backend/application/chat/executors/fast_executor.py": 320,
    "backend/application/chat/executors/fast_lanes/dispatch.py": 200,
    "backend/application/chat/executors/fast_lanes/document.py": 200,
    "backend/application/chat/executors/fast_lanes/general.py": 200,
    "backend/application/chat/executors/fast_lanes/kb.py": 200,
    "backend/application/chat/executors/fast_lanes/video.py": 200,
    "backend/application/chat/executors/fast_lanes/web.py": 200,
    "backend/application/chat/executors/fast_lanes/fast_common.py": 250,
    "backend/application/chat/executors/fast_lanes/kb_fast_impl.py": 250,
    "backend/application/chat/executors/fast_lanes/web_fast_impl.py": 250,
    "backend/application/chat/executors/fast_lanes/document_fast_impl.py": 250,
    "backend/application/chat/executors/fast_lanes/video_fast_impl.py": 250,
    "backend/application/chat/executors/fast_lanes/general_fast_impl.py": 250,
    "backend/application/chat/executors/fast_executor_result.py": 250,
    "backend/application/chat/pipeline/turn_pipeline.py": 60,
    "backend/application/chat/pipeline/session_stage.py": 80,
    "backend/application/chat/pipeline/ingress_stage.py": 120,
    "backend/application/chat/pipeline/fast_stage.py": 180,
    "backend/application/chat/pipeline/complex_stage.py": 120,
    "backend/application/chat/pipeline/complex_plan_stage.py": 80,
    "backend/application/chat/pipeline/complex_collect_stage.py": 80,
    "backend/application/chat/pipeline/complex_answer_stage.py": 100,
    "backend/application/chat/pipeline/complex_finalize_stage.py": 180,
    "backend/application/chat/pipeline/pipeline_state.py": 60,
    "backend/application/chat/executors/complex/complex_path_impl.py": 40,
    "backend/application/chat/executors/complex/complex_deadline.py": 50,
    "backend/application/chat/executors/complex/complex_multisource_impl.py": 120,
    "backend/application/chat/executors/complex/complex_feedback_impl.py": 380,
    "backend/application/chat/executors/complex/complex_feedback_gate.py": 120,
    "backend/application/chat/executors/complex/complex_feedback_refresh.py": 140,
    "backend/application/chat/executors/complex/complex_feedback_web_fetch.py": 140,
    "backend/application/chat/executors/complex/complex_feedback_synthesize.py": 80,
}


def _line_count(py_file: Path) -> int:
    return len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())


def _code_line_count(py_file: Path) -> int:
    return sum(
        1
        for line in py_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Watched module line-count guard")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Path to baseline JSON (default: tests/migration/module_size_baseline.json)",
    )
    parser.add_argument(
        "--strict-targets",
        action="store_true",
        help="Also fail when lines exceed aspirational TARGET_LIMITS (off by default).",
    )
    parser.add_argument(
        "--metric",
        choices=("all", "code"),
        default="all",
        help="Metric used for baseline/target comparison (default: all).",
    )
    parser.add_argument(
        "--report-dual",
        action="store_true",
        help="Print both physical and non-empty code lines for watched modules.",
    )
    parser.add_argument(
        "--warn-ratio",
        type=float,
        default=0.9,
        help="Warn when a module reaches this fraction of baseline (default: 0.9).",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"ERROR: baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    baseline: dict[str, dict[str, int]] = json.loads(baseline_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    warnings: list[str] = []

    for rel, limits in sorted(baseline.items()):
        py_file = ROOT / rel.replace("\\", "/")
        if not py_file.is_file():
            failures.append(f"{rel}: file missing")
            continue
        physical_lines = _line_count(py_file)
        code_lines = _code_line_count(py_file)
        current_lines = physical_lines if args.metric == "all" else code_lines
        max_lines = limits.get("lines")
        if max_lines is None:
            failures.append(f"{rel}: baseline missing 'lines'")
            continue
        if current_lines > max_lines:
            failures.append(
                f"{rel}: lines={current_lines} exceeds baseline {max_lines} "
                "(extract logic into executors/ or domain/ instead of growing this file)"
            )
        elif args.warn_ratio > 0 and current_lines >= max_lines * args.warn_ratio:
            pct = round(100 * current_lines / max_lines)
            warnings.append(
                f"{rel}: lines={current_lines} at {pct}% of baseline {max_lines} "
                "(consider splitting before hitting cap)"
            )
        target = TARGET_LIMITS.get(rel.replace("\\", "/"))
        if target is not None and current_lines > target:
            msg = f"{rel}: lines={current_lines} above target {target} (converge in R14–R15)"
            if args.strict_targets:
                failures.append(msg)
            else:
                warnings.append(msg)
        if args.report_dual:
            print(
                f"[{args.metric}] {rel}: all={physical_lines} code={code_lines} "
                f"baseline={max_lines}"
            )

    if warnings:
        print(f"[WARN] {len(warnings)} module(s) above aspirational target:\n")
        for item in warnings:
            print(f"  {item}")

    if failures:
        print(f"\n[FAIL] {len(failures)} module size violation(s):\n", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        return 1

    print(f"[OK] {len(baseline)} watched module(s) within baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
