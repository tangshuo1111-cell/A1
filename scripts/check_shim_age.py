#!/usr/bin/env python3
"""Check that no shim has outlived its planned removal phase.

Usage:
    python scripts/check_shim_age.py --current-phase P5

Exit codes:
    0  All shims are within their lifetime.
    1  One or more shims are expired (current_phase >= planned_removal_phase).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHIMS_CSV = ROOT / "docs" / "current" / "migration" / "shims.csv"

_PHASE_RE = re.compile(r"^P(\d+)$", re.IGNORECASE)


def _phase_num(phase_str: str) -> int:
    m = _PHASE_RE.match(phase_str.strip())
    if not m:
        raise ValueError(f"Invalid phase string: {phase_str!r}")
    return int(m.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Shim age checker")
    parser.add_argument(
        "--current-phase",
        required=True,
        help="Current migration phase, e.g. P5",
    )
    args = parser.parse_args()

    try:
        current = _phase_num(args.current_phase)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not SHIMS_CSV.exists():
        print(f"ERROR: shims.csv not found at {SHIMS_CSV}", file=sys.stderr)
        return 2

    expired: list[dict[str, str]] = []
    shim_active: list[dict[str, str]] = []

    with SHIMS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            shim_path = row.get("shim_path", "").strip()
            removal_phase = row.get("planned_removal_phase", "").strip()
            status = row.get("status", "").strip()

            if status in ("shim_retired",):
                continue

            if not shim_path or not removal_phase:
                continue

            try:
                removal = _phase_num(removal_phase)
            except ValueError:
                print(
                    f"WARNING: skipping row with invalid planned_removal_phase={removal_phase!r}",
                    file=sys.stderr,
                )
                continue

            file_exists = (ROOT / shim_path).exists()
            if status == "shim_active" or file_exists:
                if current >= removal:
                    expired.append(row)
                else:
                    shim_active.append(row)

    if expired:
        print(
            f"\n[FAIL] {len(expired)} expired shim(s) found (current={args.current_phase}):\n",
            file=sys.stderr,
        )
        for row in expired:
            print(
                f"  EXPIRED  {row['shim_path']}  "
                f"planned_removal={row['planned_removal_phase']}  "
                f"replacement={row.get('replacement_path', '?')}",
                file=sys.stderr,
            )
        print(
            "\nClean up these shims before proceeding to the next phase.",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] {len(shim_active)} active shim(s), none expired at {args.current_phase}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
