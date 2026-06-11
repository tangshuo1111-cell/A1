#!/usr/bin/env python3
"""Non-chat module line-count guard (R20 governance spread).

Watches storage / workers / tasks entrypoints with the same baseline discipline as chat.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "tests" / "migration" / "non_chat_module_size_baseline.json"


def _line_count(py_file: Path) -> int:
    return len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-chat watched module line-count guard")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_file():
        print(f"ERROR: baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    baseline: dict[str, dict[str, int]] = json.loads(baseline_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for rel, limits in sorted(baseline.items()):
        py_file = ROOT / rel.replace("\\", "/")
        if not py_file.is_file():
            failures.append(f"{rel}: file missing")
            continue
        current = _line_count(py_file)
        cap = limits.get("lines")
        if cap is None:
            failures.append(f"{rel}: baseline missing 'lines'")
            continue
        if current > cap:
            failures.append(f"{rel}: lines={current} exceeds baseline {cap}")

    if failures:
        print(f"[FAIL] {len(failures)} non-chat module size violation(s):", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        return 1

    print(f"[OK] {len(baseline)} non-chat watched module(s) within baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
