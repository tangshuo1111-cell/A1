#!/usr/bin/env python3
"""Freeze legacy chat entry modules — metrics must not grow (Round 0 guard).

Baseline: tests/migration/frozen_chat_modules_baseline.json

Checked per file:
  - total lines (non-empty lines in source)
  - top-level function count
  - public top-level function count (no leading underscore)
  - all function count (including nested)
  - sum cyclomatic complexity (all functions)
  - max cyclomatic complexity (single function)

Usage:
    python scripts/check_frozen_chat_modules.py [--baseline PATH]

Exit codes:
    0  All frozen modules within baseline.
    1  One or more metrics exceeded baseline.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "tests" / "migration" / "frozen_chat_modules_baseline.json"

MetricKey = str


def _cyclomatic_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1
    return score


def _metrics(py_file: Path) -> dict[MetricKey, int]:
    source = py_file.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(py_file))
    top_funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    all_funcs = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    per_func = [_cyclomatic_complexity(n) for n in all_funcs]
    public_top = [n for n in top_funcs if not n.name.startswith("_")]
    return {
        "lines": len(source.splitlines()),
        "top_level_functions": len(top_funcs),
        "public_top_level_functions": len(public_top),
        "all_functions": len(all_funcs),
        "sum_cyclomatic_complexity": sum(per_func) if per_func else 0,
        "max_cyclomatic_complexity": max(per_func) if per_func else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen chat module metrics guard")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Path to baseline JSON (default: tests/migration/frozen_chat_modules_baseline.json)",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"ERROR: baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    baseline: dict[str, dict[str, int]] = json.loads(baseline_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for rel, limits in sorted(baseline.items()):
        py_file = ROOT / rel.replace("/", "\\") if "\\" not in rel else ROOT / rel
        if not py_file.is_file():
            failures.append(f"{rel}: file missing")
            continue
        current = _metrics(py_file)
        for key, limit in limits.items():
            value = current.get(key)
            if value is None:
                failures.append(f"{rel}: unknown metric {key!r} in baseline")
                continue
            if value > limit:
                failures.append(
                    f"{rel}: {key}={value} exceeds baseline {limit} "
                    f"(do not add main logic here; use turn_orchestrator / executors)"
                )

    if failures:
        print(f"\n[FAIL] {len(failures)} frozen module violation(s):\n", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        print(
            "\nFrozen modules are legacy entry points. New work belongs in "
            "turn_orchestrator.py and executors/ (Round 1+).",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] {len(baseline)} frozen chat module(s) within baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
