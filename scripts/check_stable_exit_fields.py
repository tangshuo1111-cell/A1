#!/usr/bin/env python3
"""Static guard for promoted stable evaluation fields.

This check is intentionally narrower than business contract tests:
- it only guards fields that evaluation has promoted out of fragile-only status
- it does not require every field on every response
- it verifies that each promoted field still has a discoverable backend write path

Exit codes:
    0  All promoted fields have at least one backend write path.
    1  One or more promoted fields lost their backend write path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROMOTED_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "commit_status": (
        r'"commit_status"\s*:',
        r"commit_status=",
    ),
    "kb_hits": (r'"kb_hits"\s*:',),
    "background_task_id": (
        r'"background_task_id"\s*:',
        r"resolve_background_task_id",
    ),
}


def _backend_sources() -> list[Path]:
    return [
        path for path in sorted((ROOT / "backend").rglob("*.py")) if "__pycache__" not in path.parts
    ]


def _matches_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def main() -> int:
    backend_files = _backend_sources()
    missing: list[str] = []
    for field_name, patterns in PROMOTED_FIELD_PATTERNS.items():
        found = False
        for path in backend_files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if _matches_any_pattern(text, patterns):
                found = True
                break
        if not found:
            missing.append(field_name)

    if missing:
        print("ERROR: promoted stable eval fields lost backend write paths:", file=sys.stderr)
        for field_name in missing:
            print(f"  - {field_name}", file=sys.stderr)
        return 1

    print(
        "OK: promoted stable eval fields still have backend write paths "
        f"({', '.join(sorted(PROMOTED_FIELD_PATTERNS))})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
