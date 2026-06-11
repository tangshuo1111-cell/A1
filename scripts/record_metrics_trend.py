#!/usr/bin/env python3
"""Append in-process metrics snapshot to JSONL for local long-term trend (R22)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DEFAULT_OUT = ROOT / "data" / "observability" / "metrics_trend.jsonl"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(description="Record metrics snapshot trend line")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="JSONL output path (default: data/observability/metrics_trend.jsonl)",
    )
    args = parser.parse_args()

    from observability import metrics_snapshot

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snap = metrics_snapshot()
    row = {"ts": int(time.time()), **snap}
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[OK] recorded metrics trend -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
