#!/usr/bin/env python3
"""Warn/fail if text-only eval rules outlive the migration window.

Text-only means a case defines `must_not_happen` but no explicit
`must_not_happen_rule_ids`.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RETIREMENT_CSV = ROOT / "docs" / "current" / "migration" / "compat_retirement.csv"
CASES_DIR = ROOT / "tests" / "evaluation" / "cases"
_RELEASE_RE = re.compile(r"^S(\d+)$", re.IGNORECASE)


def _release_num(value: str) -> int:
    match = _RELEASE_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid release tag: {value!r}")
    return int(match.group(1))


def _delete_by_release() -> str | None:
    if not RETIREMENT_CSV.exists():
        return None
    with RETIREMENT_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("item_id", "").strip() == "eval_case_text_rule_fallback":
                return row.get("delete_by_release", "").strip() or None
    return None


def _text_only_cases() -> list[str]:
    matches: list[str] = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            has_text = bool(item.get("must_not_happen"))
            has_ids = bool(item.get("must_not_happen_rule_ids"))
            if has_text and not has_ids:
                matches.append(f"{path.name}:{item.get('case_id', '<missing-case-id>')}")
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description="Check age of text-only eval rules")
    parser.add_argument("--current-release", required=True, help="Current release tag, e.g. S14")
    args = parser.parse_args()

    try:
        current = _release_num(args.current_release)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    delete_by = _delete_by_release()
    if not delete_by:
        print("WARNING: eval_case_text_rule_fallback not registered in compat_retirement.csv")
        return 0

    try:
        delete_num = _release_num(delete_by)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    text_only = _text_only_cases()
    if text_only and current >= delete_num:
        print(
            f"ERROR: found {len(text_only)} text-only eval cases past retirement window ({args.current_release} >= {delete_by}):",
            file=sys.stderr,
        )
        for item in text_only:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        f"OK: text-only eval cases={len(text_only)}; "
        f"retirement gate={delete_by}; current={args.current_release}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
