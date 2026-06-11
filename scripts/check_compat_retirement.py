#!/usr/bin/env python3
"""Ensure compat_retirement.csv items are retired by their delete_by_release.

Usage:
    python scripts/check_compat_retirement.py --current-release S13

Exit codes:
    0  All due items are retired (or not yet due).
    1  One or more items are overdue and still not retired.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPAT_CSV = ROOT / "docs" / "current" / "migration" / "compat_retirement.csv"

_RELEASE_RE = re.compile(r"^S(\d+)$", re.IGNORECASE)


def _release_num(release_str: str) -> int:
    m = _RELEASE_RE.match(release_str.strip())
    if not m:
        raise ValueError(f"Invalid release string: {release_str!r}")
    return int(m.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compat retirement deadline checker")
    parser.add_argument(
        "--current-release",
        required=True,
        help="Current plan release, e.g. S13",
    )
    args = parser.parse_args()

    try:
        current = _release_num(args.current_release)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not COMPAT_CSV.exists():
        print(f"ERROR: compat_retirement.csv not found at {COMPAT_CSV}", file=sys.stderr)
        return 2

    overdue: list[dict[str, str]] = []
    pending_count = 0

    with COMPAT_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "").strip()
            delete_by = row.get("delete_by_release", "").strip()
            if not delete_by:
                continue
            if status == "retired":
                continue
            pending_count += 1
            try:
                due = _release_num(delete_by)
            except ValueError:
                print(
                    f"WARNING: skipping row with invalid delete_by_release={delete_by!r}",
                    file=sys.stderr,
                )
                continue
            if current >= due:
                overdue.append(row)

    if overdue:
        print("ERROR: overdue compat items not yet retired:", file=sys.stderr)
        for row in overdue:
            print(
                f"  {row.get('item_type')}:{row.get('item_id')} "
                f"(delete_by={row.get('delete_by_release')}, status={row.get('status')})",
                file=sys.stderr,
            )
        return 1

    print(f"OK: {pending_count} pending item(s); none overdue for release {args.current_release}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
