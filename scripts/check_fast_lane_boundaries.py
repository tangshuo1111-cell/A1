#!/usr/bin/env python3
"""Fast lane import boundary guard (Round 9).

``executors/fast_lanes`` must not pull complex executor internals or agent entities.

Usage:
    python scripts/check_fast_lane_boundaries.py [--backend-root backend]

Exit codes:
    0  No violations.
    1  Forbidden imports found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
FAST_LANES = "application/chat/executors/fast_lanes"
FORBIDDEN_PREFIXES = (
    "application.chat.executors.complex",
    "application.chat.executors.complex_executor",
    "agents.main_agent",
    "agents.middle_agent",
    "agents.answer_agent",
)


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            hits.append((node.lineno, node.module))
    return hits


def _is_forbidden(mod: str) -> bool:
    for prefix in FORBIDDEN_PREFIXES:
        if mod == prefix or mod.startswith(prefix + "."):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast lane import boundary checker")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend = ROOT / args.backend_root
    lane_root = backend / Path(FAST_LANES)
    violations: list[str] = []

    if not lane_root.is_dir():
        print(f"ERROR: missing {lane_root}", file=sys.stderr)
        return 2

    for py in sorted(lane_root.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        rel = py.relative_to(backend).as_posix()
        for lineno, mod in _imports(py):
            if _is_forbidden(mod):
                violations.append(f"{rel}:{lineno} imports {mod}")

    if violations:
        print("[FAIL] fast lane boundary violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("[OK] fast_lanes do not import complex executor or agent entities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
