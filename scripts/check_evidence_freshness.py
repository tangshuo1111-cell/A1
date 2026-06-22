#!/usr/bin/env python3
"""C-level warning: real validation evidence older than threshold days.

Does NOT hard-fail CI — reminds that manual real regression / external smoke
should be re-run. See docs/evidence/project_validation_summary.md.

Usage:
    python scripts/check_evidence_freshness.py [--max-age-days 30]

Exit codes:
    0  Fresh enough, or only warnings printed.
    0  Always 0 (warning-only guard).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_EVIDENCE_FILES = (
    ROOT / "docs" / "evidence" / "project_validation_summary.md",
    ROOT / "docs" / "evidence" / "real_regression_validation_report.md",
    ROOT / "docs" / "evidence" / "real_external_validation_report.md",
)

_LATEST_RUN_RE = re.compile(
    r"最新复跑[：:]\s*(\d{4}-\d{2}-\d{2})",
)


def _parse_latest_run(text: str) -> date | None:
    match = _LATEST_RUN_RE.search(text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence freshness warning (C-level)")
    parser.add_argument("--max-age-days", type=int, default=30)
    args = parser.parse_args()

    today = datetime.now(tz=UTC).date()
    warnings: list[str] = []

    for path in _EVIDENCE_FILES:
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            warnings.append(f"{rel}: missing (cannot check freshness)")
            continue
        latest = _parse_latest_run(path.read_text(encoding="utf-8"))
        if latest is None:
            warnings.append(f"{rel}: no `最新复跑：YYYY-MM-DD` marker")
            continue
        age = (today - latest).days
        if age > args.max_age_days:
            warnings.append(
                f"{rel}: latest run {latest.isoformat()} is {age} days old "
                f"(threshold {args.max_age_days}) — re-run real regression / external smoke"
            )

    if warnings:
        print("[WARN] evidence freshness (C-level, non-blocking):", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
    else:
        print(f"[OK] evidence freshness (all within {args.max_age_days} days).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
