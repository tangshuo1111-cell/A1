#!/usr/bin/env python3
"""Guard: eval cases must not use top-level ``required_trace_fields``.

Fragile trace checks belong under ``expected.warning_assertions`` (C-level warning only).
See docs/evidence/eval_governance_guardrails.md.

Usage:
    python scripts/check_eval_observability_fields.py

Exit codes:
    0  No violations.
    1  Top-level required_trace_fields found in case YAML.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "tests" / "evaluation" / "cases"

# Indent under ``expected:`` but NOT under ``warning_assertions:``.
_TOP_LEVEL_TRACE_RE = re.compile(
    r"^(\s*)required_trace_fields\s*:",
    re.MULTILINE,
)


def _is_under_warning_assertions(lines: list[str], match_line: int) -> bool:
    """True if the matched line sits under a warning_assertions block."""
    indent = len(_TOP_LEVEL_TRACE_RE.match(lines[match_line]).group(1))  # type: ignore[union-attr]
    for i in range(match_line - 1, -1, -1):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent < indent and "warning_assertions" in line:
            return True
        if cur_indent < indent and line.rstrip().endswith(":"):
            return False
    return False


def main() -> int:
    violations: list[str] = []

    for path in sorted(CASES_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if not _TOP_LEVEL_TRACE_RE.match(line):
                continue
            if _is_under_warning_assertions(lines, idx):
                continue
            rel = path.relative_to(ROOT).as_posix()
            violations.append(f"{rel}:{idx + 1}: move required_trace_fields under warning_assertions")

    if violations:
        print("[FAIL] eval observability field violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(f"[OK] eval case observability fields ({len(list(CASES_DIR.glob('*.yaml')))} YAML files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
