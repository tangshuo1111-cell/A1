#!/usr/bin/env python3
"""Ensure chat pipeline stages do not use lazy _ChatFacade monkeypatch anchors."""

from __future__ import annotations

import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "backend" / "application" / "chat" / "pipeline"
FORBIDDEN = ("class _ChatFacade", "facade = _ChatFacade()", "def __getattr__")


def main() -> int:
    violations: list[str] = []
    for py in sorted(PIPELINE.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                violations.append(f"{py.relative_to(ROOT)}: contains {token!r}")
    if violations:
        print("[FAIL] pipeline facade remnants:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("[OK] pipeline stages use direct canonical imports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
