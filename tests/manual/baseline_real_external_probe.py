#!/usr/bin/env python3
"""Optional real-external perf probe (manual / CI nightly).

Requires network + external APIs. Skip in default pytest via marker `real_external`.

Usage:
    py tests/manual/baseline_real_external_probe.py --sample kb_query_simple_001
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from tests.baselines._support.perf_probe import load_samples, run_sample_perf  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Real external perf baseline probe")
    parser.add_argument("--sample", default="kb_query_simple_001")
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    args = parser.parse_args()
    sample = next((s for s in load_samples() if s["sample_id"] == args.sample), None)
    if sample is None:
        print(f"unknown sample: {args.sample}", file=sys.stderr)
        return 2
    t0 = time.perf_counter()
    row = run_sample_perf(sample)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    print(
        f"sample={row.sample_id} elapsed_ms={elapsed_ms} "
        f"first_ms={row.first_response_ms} success={row.success} lane={row.lane} mode={row.mode}"
    )
    if not row.success:
        return 1
    if elapsed_ms > args.timeout_sec * 1000:
        print(f"SLA exceeded: {elapsed_ms}ms > {args.timeout_sec}s", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
