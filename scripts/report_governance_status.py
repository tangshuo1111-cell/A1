#!/usr/bin/env python3
"""One-shot governance status report (Round 11).

Runs watched guard scripts and prints module line counts from baseline.

Usage:
    python scripts/report_governance_status.py

Exit codes:
    0  All guards passed.
    1  One or more guards failed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "tests" / "migration" / "module_size_baseline.json"

GUARD_SCRIPTS = (
    "check_module_size.py",
    "check_import_boundaries.py",
    "check_compat_shims.py",
    "check_history_context_imports.py",
    "check_pending_store_imports.py",
    "check_compat_consumption.py",
    "check_no_pipeline_facade.py",
    "check_fast_lane_boundaries.py",
    "audit_test_patch_depth.py",
    "audit_migration_ledgers.py",
    "check_non_chat_module_size.py",
    "check_observability_health.py",
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _code_line_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def _git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return "unknown"
    return (proc.stdout or "").strip() or "unknown"


def main() -> int:
    print(f"=== Governance status @ {_git_head()} ===")
    print("Line metrics: baseline uses all physical lines; human review uses non-empty code lines.\n")
    print("=== Governance guards ===")
    failed = False
    for name in GUARD_SCRIPTS:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        status = "OK" if proc.returncode == 0 else "FAIL"
        print(f"[{status}] {name}")
        out = (proc.stdout or proc.stderr or "").strip()
        if out:
            for line in out.splitlines()[:3]:
                print(f"       {line}")
        if proc.returncode != 0:
            failed = True
            if proc.stderr and proc.stderr.strip() not in (out or ""):
                for line in proc.stderr.strip().splitlines()[:5]:
                    print(f"       ! {line}")

    print("\n=== Watched module sizes (baseline snapshot) ===")
    if BASELINE.is_file():
        baseline: dict[str, dict[str, int]] = json.loads(BASELINE.read_text(encoding="utf-8"))
        rows: list[tuple[str, int, int, int]] = []
        for rel, limits in sorted(baseline.items()):
            py = ROOT / rel.replace("\\", "/")
            if not py.is_file():
                continue
            current = _line_count(py)
            current_code = _code_line_count(py)
            cap = limits.get("lines", current)
            rows.append((rel, current, current_code, cap))
        for rel, current, current_code, cap in rows:
            flag = " !" if current > cap else ""
            print(f"  all={current:4d} / {cap:4d}{flag}  code={current_code:4d}  {rel}")
        print(f"\nTotal watched modules: {len(rows)}")
    else:
        print(f"  (baseline missing: {BASELINE})")
        failed = True

    if failed:
        print("\n[FAIL] governance status check failed.", file=sys.stderr)
        return 1

    print("\n[OK] governance status healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
