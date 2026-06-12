#!/usr/bin/env python3
"""Block production imports of deprecated ``agents.history_context`` shim.

Canonical: ``domain.session_types`` (agents layer may use ``agents.shared.history_context`` re-export).

Usage:
    python scripts/check_history_context_imports.py [--backend-root backend]

Exit codes:
    0  No forbidden imports in production paths.
    1  Violations found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = frozenset({"agents.history_context", "compat.history_context"})
APPLICATION_CHAT_FORBIDDEN = frozenset({"agents.shared.history_context"})
SKIP_PARTS = frozenset({"tests", "compat", "__pycache__"})
ALLOWED_FILES = frozenset(
    {
        "agents/history_context.py",
        "compat/history_context.py",
    }
)


def _imports(path: Path, *, backend_root: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    rel = path.relative_to(backend_root).as_posix()
    forbid_shared = rel.startswith("application/chat/")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN or alias.name.startswith("agents.history_context."):
                    hits.append((node.lineno, alias.name))
                if forbid_shared and (
                    alias.name in APPLICATION_CHAT_FORBIDDEN
                    or alias.name.startswith("agents.shared.history_context.")
                ):
                    hits.append((node.lineno, f"{alias.name} (use domain.session_types)"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod in FORBIDDEN or mod.startswith("agents.history_context."):
                hits.append((node.lineno, mod))
            if forbid_shared and (
                mod in APPLICATION_CHAT_FORBIDDEN
                or mod.startswith("agents.shared.history_context.")
            ):
                hits.append((node.lineno, f"{mod} (use domain.session_types)"))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="agents.history_context import guard")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend = ROOT / args.backend_root
    violations: list[str] = []

    for py in sorted(backend.rglob("*.py")):
        rel = py.relative_to(backend).as_posix()
        if any(part in SKIP_PARTS for part in py.parts):
            continue
        if rel in ALLOWED_FILES:
            continue
        for lineno, mod in _imports(py, backend_root=backend):
            violations.append(f"{rel}:{lineno} imports {mod}")

    if violations:
        print("[FAIL] deprecated history_context imports in production:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(
        "[OK] production code avoids deprecated history_context shims (canonical: domain.session_types)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
