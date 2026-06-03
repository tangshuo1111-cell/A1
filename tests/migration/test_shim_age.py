"""Shim lifecycle tests.

Validates §15.9 Shim SLA rules:
- shims.csv exists and is parseable.
- All active shims have valid planned_removal_phase values.
- Shims do not outlive their planned phase (relative to the phase constant in this file).
- All shim_path files that exist contain the DEPRECATED_COMPAT_SHIM marker.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHIMS_CSV = PROJECT_ROOT / "docs" / "current" / "migration" / "shims.csv"
CURRENT_PHASE = "P5"   # Update this as each phase completes.

_PHASE_RE = re.compile(r"^P(\d+)$", re.IGNORECASE)
DEPRECATED_MARKER = "DEPRECATED_COMPAT_SHIM"


def _phase_num(phase_str: str) -> int:
    m = _PHASE_RE.match(phase_str.strip())
    assert m, f"Invalid phase string: {phase_str!r}"
    return int(m.group(1))


def _load_shims() -> list[dict[str, str]]:
    rows = []
    with SHIMS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


class TestShimsCsvStructure:
    def test_shims_csv_exists(self):
        assert SHIMS_CSV.exists(), f"shims.csv not found at {SHIMS_CSV}"

    def test_shims_csv_has_required_columns(self):
        rows = _load_shims()
        if not rows:
            return
        required = {"shim_path", "introduced_phase", "planned_removal_phase", "replacement_path", "owner", "status"}
        assert required.issubset(set(rows[0].keys())), (
            f"Missing columns: {required - set(rows[0].keys())}"
        )

    def test_all_phases_valid_format(self):
        for row in _load_shims():
            intro = row.get("introduced_phase", "").strip()
            removal = row.get("planned_removal_phase", "").strip()
            if intro:
                assert _PHASE_RE.match(intro), f"Bad introduced_phase: {intro!r} in {row['shim_path']}"
            if removal:
                assert _PHASE_RE.match(removal), f"Bad planned_removal_phase: {removal!r} in {row['shim_path']}"

    def test_removal_phase_after_intro_phase(self):
        for row in _load_shims():
            intro = row.get("introduced_phase", "").strip()
            removal = row.get("planned_removal_phase", "").strip()
            if intro and removal:
                assert _phase_num(removal) >= _phase_num(intro), (
                    f"planned_removal_phase {removal} is before introduced_phase {intro} "
                    f"in {row['shim_path']}"
                )

    def test_status_values_are_valid(self):
        valid = {"shim_active", "shim_retired"}
        for row in _load_shims():
            status = row.get("status", "").strip()
            assert status in valid, f"Unknown status {status!r} in {row['shim_path']}"


class TestShimNotExpired:
    @pytest.mark.parametrize("row", _load_shims() if SHIMS_CSV.exists() else [])
    def test_shim_not_expired_at_current_phase(self, row: dict[str, str]):
        status = row.get("status", "").strip()
        if status == "shim_retired":
            return
        removal = row.get("planned_removal_phase", "").strip()
        if not removal:
            return
        current = _phase_num(CURRENT_PHASE)
        planned = _phase_num(removal)
        assert current < planned, (
            f"EXPIRED SHIM: {row['shim_path']} was due for removal at {removal} "
            f"but current phase is {CURRENT_PHASE}. Run the shim deletion checklist."
        )


class TestShimFileHasDeprecatedMarker:
    @pytest.mark.parametrize("row", _load_shims() if SHIMS_CSV.exists() else [])
    def test_active_shim_has_marker(self, row: dict[str, str]):
        status = row.get("status", "").strip()
        if status != "shim_active":
            return
        shim_path = PROJECT_ROOT / row.get("shim_path", "")
        if not shim_path.exists():
            pytest.skip(f"Shim file not found on disk: {shim_path.relative_to(PROJECT_ROOT)}")
        content = shim_path.read_text(encoding="utf-8", errors="replace")
        assert DEPRECATED_MARKER in content, (
            f"Active shim {row['shim_path']} is missing the {DEPRECATED_MARKER!r} marker. "
            f"Add it as a comment at the top of the file."
        )
