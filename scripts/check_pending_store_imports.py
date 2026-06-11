#!/usr/bin/env python3
"""Block production imports of deprecated ``rag.pending_store`` facade."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = frozenset({"rag.pending_store"})
SKIP_PARTS = frozenset({"tests", "compat", "__pycache__", "rag"})
ALLOWED_FILES = frozenset(
    {
        "rag/pending_store.py",
    }
)


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN or alias.name.startswith("rag.pending_store."):
                    hits.append((node.lineno, alias.name))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module in FORBIDDEN or node.module.startswith("rag.pending_store."))
        ):
            hits.append((node.lineno, node.module))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="rag.pending_store import guard")
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
        for lineno, mod in _imports(py):
            violations.append(f"{rel}:{lineno} imports {mod}")

    if violations:
        print("[FAIL] deprecated pending_store imports in production:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1

    print("[OK] production code avoids deprecated rag.pending_store facade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
