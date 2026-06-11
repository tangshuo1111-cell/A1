#!/usr/bin/env python3
"""Verify README/AGENTS docs do not reference missing backend paths (Round 0+).

Scans markdown for backtick-quoted paths under backend/ and application/chat/.

Usage:
    python scripts/check_readme_paths.py [--root PATH]

Exit codes:
    0  All referenced paths exist (or are directory prefixes with children).
    1  One or more dead references found.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent

DOC_GLOBS = (
    "README.md",
    "AGENTS.md",
    "backend/application/README.md",
    "backend/application/chat/README.md",
    "backend/application/ingress/README.md",
)

# Retired paths that must not appear in active docs.
RETIRED_PATH_FRAGMENTS = (
    "fast_path_entry.py",
    "complex_path_entry.py",
    "async_entry.py",
)

PATH_PATTERN = re.compile(r"`((?:backend|application)/[a-zA-Z0-9_./\-]+)`")


def _resolve_ref(ref: str) -> Path:
    ref = ref.strip().rstrip("/")
    if ref.startswith("application/"):
        return ROOT / "backend" / ref
    return ROOT / ref


def _path_ok(path: Path) -> bool:
    if path.is_file():
        return True
    if path.is_dir():
        return True
    # Allow directory refs without trailing slash if parent exists as dir prefix
    parent = path.parent
    return parent.is_dir() and any(parent.iterdir())


def _scan_file(md_path: Path) -> list[str]:
    violations: list[str] = []
    text = md_path.read_text(encoding="utf-8", errors="replace")
    rel_doc = md_path.relative_to(ROOT).as_posix()

    for fragment in RETIRED_PATH_FRAGMENTS:
        if fragment in text:
            violations.append(f"{rel_doc}: mentions retired path {fragment!r}")

    for match in PATH_PATTERN.finditer(text):
        ref = match.group(1)
        target = _resolve_ref(ref)
        if not _path_ok(target):
            violations.append(f"{rel_doc}: missing path {ref!r}")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="README path existence checker")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root)

    violations: list[str] = []
    for pattern in DOC_GLOBS:
        path = root / pattern
        if path.is_file():
            violations.extend(_scan_file(path))

    if violations:
        print(f"\n[FAIL] {len(violations)} README path issue(s):\n", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        return 1

    print(f"[OK] {len(DOC_GLOBS)} doc file(s) checked; no dead path references.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
