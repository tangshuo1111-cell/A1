#!/usr/bin/env python3
"""Audit migration ledger CSVs for retired-path consistency.

Checks:
  - docs/current/migration/legacy_paths_status.csv has required columns
  - docs/current/migration/file_mapping.csv targets exist or are marked retired

Usage:
    python scripts/audit_migration_ledgers.py

Exit codes:
    0  Ledgers consistent.
    1  Violations found.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "current" / "migration"
LEGACY_CSV = DOCS / "legacy_paths_status.csv"
MAPPING_CSV = DOCS / "file_mapping.csv"
SKIP_TARGET_MARKERS = frozenset({"原位", "in-place", "same"})
RETIRED_STATUSES = frozenset({"retired", "removed", "deleted", "done"})


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _resolve_target(raw: str) -> Path | None:
    text = (raw or "").strip()
    if not text or text in SKIP_TARGET_MARKERS:
        return None
    if text.endswith("/") or text.endswith("\\"):
        return ROOT / text.rstrip("/\\")
    return ROOT / text


def main() -> int:
    violations: list[str] = []

    if not LEGACY_CSV.is_file():
        violations.append(f"missing ledger: {LEGACY_CSV.relative_to(ROOT)}")
    if not MAPPING_CSV.is_file():
        violations.append(f"missing ledger: {MAPPING_CSV.relative_to(ROOT)}")

    if LEGACY_CSV.is_file():
        rows = _read_csv(LEGACY_CSV)
        if not rows:
            violations.append("legacy_paths_status.csv is empty")
        else:
            required = {"legacy_path", "status"}
            missing_cols = required - set(rows[0].keys())
            if missing_cols:
                violations.append(f"legacy_paths_status.csv missing columns: {sorted(missing_cols)}")
            for row in rows:
                path = (row.get("legacy_path") or "").strip()
                status = (row.get("status") or "").strip().lower()
                if not path:
                    continue
                if status == "active" and not (ROOT / path).exists():
                    violations.append(f"legacy path marked active but missing: {path}")

    if MAPPING_CSV.is_file():
        rows = _read_csv(MAPPING_CSV)
        for row in rows:
            source = (row.get("source_path") or row.get("old_path") or "").strip()
            target_raw = (row.get("target_path") or row.get("new_path") or "").strip()
            status = (row.get("status") or "").strip().lower()
            action = (row.get("action") or "").strip().lower()
            if "{" in source or "}" in source:
                continue
            if status in RETIRED_STATUSES or action in {"retired", "removed", "deleted"}:
                continue
            target = _resolve_target(target_raw)
            if target is None:
                continue
            if target.is_dir():
                continue
            if not target.exists():
                violations.append(f"file_mapping target missing: {target_raw} (from {source or '?'})")

    if violations:
        print("[FAIL] migration ledger violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    legacy_n = len(_read_csv(LEGACY_CSV)) if LEGACY_CSV.is_file() else 0
    mapping_n = len(_read_csv(MAPPING_CSV)) if MAPPING_CSV.is_file() else 0
    print(f"[OK] migration ledgers consistent (legacy={legacy_n}, mapping={mapping_n}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
