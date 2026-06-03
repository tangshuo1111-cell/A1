#!/usr/bin/env python3
"""Recapture perf baselines for the new architecture path (P0/P10).

Runs all Phase-0 baseline samples through ingress v2 + fast/complex lanes with
deterministic external-IO mocks, then writes:
  - docs/current/baselines/perf_baseline.csv
  - docs/current/baselines/perf_baseline_meta.yaml

Usage:
    py scripts/recapture_perf_baseline.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = ROOT / "docs" / "current" / "baselines"
PERF_CSV = BASELINE_DIR / "perf_baseline.csv"
LEGACY_CSV = BASELINE_DIR / "perf_baseline_legacy.csv"
META_YAML = BASELINE_DIR / "perf_baseline_meta.yaml"

if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.baselines._support.perf_probe import run_all_samples  # noqa: E402


def _write_csv(rows: list, path: Path) -> None:
    fieldnames = [
        "sample_id",
        "first_response_ms",
        "total_ms",
        "llm_calls",
        "tool_calls",
        "token_in",
        "token_out",
        "success",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sample_id": row.sample_id,
                    "first_response_ms": row.first_response_ms,
                    "total_ms": row.total_ms,
                    "llm_calls": row.llm_calls,
                    "tool_calls": row.tool_calls,
                    "token_in": row.token_in,
                    "token_out": row.token_out,
                    "success": str(row.success).lower(),
                }
            )


def _write_meta(rows: list) -> None:
    captured_at = datetime.now(tz=UTC).isoformat()
    lines = [
        "catalog_version: 1",
        f'captured_at: "{captured_at}"',
        'architecture_path: "ingress_v2_fast_complex_lanes"',
        'capture_tool: "scripts/recapture_perf_baseline.py"',
        "external_io: mocked",
        "notes:",
        '  - "Measures new-path orchestration latency with deterministic mocks."',
        '  - "Legacy pre-migration estimates archived in perf_baseline_legacy.csv when present."',
        "samples:",
    ]
    for row in rows:
        lines.append(f"  {row.sample_id}:")
        lines.append(f'    lane: "{row.lane}"')
        lines.append(f'    mode: "{row.mode}"')
        lines.append(f"    first_response_ms: {row.first_response_ms}")
        lines.append(f"    total_ms: {row.total_ms}")
    META_YAML.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Recapture perf baselines")
    parser.add_argument("--dry-run", action="store_true", help="Print rows without writing files")
    args = parser.parse_args()

    rows = run_all_samples()
    if not rows:
        print("[FAIL] no baseline samples captured", file=sys.stderr)
        return 1
    if not all(row.success for row in rows):
        failed = [row.sample_id for row in rows if not row.success]
        print(f"[FAIL] samples failed: {failed}", file=sys.stderr)
        return 1

    if args.dry_run:
        for row in rows:
            print(
                f"{row.sample_id}\tfirst={row.first_response_ms}\ttotal={row.total_ms}"
                f"\tlane={row.lane}\tmode={row.mode}\tok={row.success}"
            )
        return 0

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    if PERF_CSV.exists() and not LEGACY_CSV.exists():
        shutil.copy2(PERF_CSV, LEGACY_CSV)
    _write_csv(rows, PERF_CSV)
    _write_meta(rows)
    print(f"[OK] wrote {PERF_CSV} ({len(rows)} rows)")
    print(f"[OK] wrote {META_YAML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
