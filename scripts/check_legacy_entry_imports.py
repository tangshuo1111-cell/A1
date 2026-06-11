#!/usr/bin/env python3
"""Block production imports of legacy chat entry modules (Cleanup C0+).

Forbidden in production paths:
  application.chat.fast_path_entry
  application.chat.complex_path_entry
  application.chat.async_entry

Allowed: tests/, backend/compat/, and thin re-export shells under application/chat/
  that only re-export (enforced separately by line-count baseline).

Usage:
    python scripts/check_legacy_entry_imports.py [--backend-root backend]

Exit codes:
    0  No forbidden production imports.
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

FORBIDDEN_MODULES = frozenset(
    {
        "application.chat.fast_path_entry",
        "application.chat.complex_path_entry",
        "application.chat.async_entry",
    }
)

PRODUCTION_PREFIXES = (
    "backend/application/",
    "backend/agents/",
    "backend/services/",
    "backend/api/",
)

SKIP_DIR_NAMES = frozenset({"tests", "compat", "__pycache__"})

# Re-export shells may import canonical impl during transition; not checked here.
REEXPORT_SHELLS = frozenset(
    {
        "backend/application/chat/turn_orchestrator.py",
        "backend/application/chat/run_chat_turn.py",
    }
)


def _is_production_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if rel in REEXPORT_SHELLS:
        return False
    return rel.startswith(PRODUCTION_PREFIXES) and path.suffix == ".py"


def _imports_in_file(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod in FORBIDDEN_MODULES or any(
                    mod.startswith(f"{m}.") for m in FORBIDDEN_MODULES
                ):
                    hits.append((node.lineno, mod))
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod in FORBIDDEN_MODULES or any(
                mod.startswith(f"{m}.") for m in FORBIDDEN_MODULES
            ):
                hits.append((node.lineno, mod))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy entry import guard")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend = ROOT / args.backend_root
    violations: list[str] = []

    for py_file in sorted(backend.rglob("*.py")):
        if not _is_production_file(py_file):
            continue
        rel = py_file.relative_to(ROOT).as_posix()
        for lineno, mod in _imports_in_file(py_file):
            violations.append(f"{rel}:{lineno}: imports forbidden legacy entry {mod}")

    if violations:
        print(f"\n[FAIL] {len(violations)} legacy entry import(s):\n", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        print(
            "\nImport executors/fast_lanes/*, executors/complex/*, executors/async/* instead.",
            file=sys.stderr,
        )
        return 1

    print("[OK] no forbidden legacy entry imports in production paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
