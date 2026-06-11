#!/usr/bin/env python3
"""Block os.getenv in business layers — config must go through settings (Round 11).

Scans backend/agents and backend/application for direct os.getenv / os.environ.get.

Usage:
    python scripts/check_direct_getenv.py [--backend-root backend]

Exit codes:
    0  No violations.
    1  Direct env access detected.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_PREFIXES = (
    "agents",
    "application",
    "services",
    "api",
)

GRANDFATHER_FILES: frozenset[str] = frozenset()


def _scan_file(path: Path, backend: Path) -> list[str]:
    rel = path.relative_to(backend).as_posix()
    if rel in GRANDFATHER_FILES:
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []

    hits: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"getenv", "get"}:
                base = node.func.value
                if isinstance(base, ast.Name) and base.id == "os":
                    hits.append(f"{rel}:{node.lineno}: os.{node.func.attr}(...)")
            self.generic_visit(node)

    _Visitor().visit(tree)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct getenv guard")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend = ROOT / args.backend_root
    violations: list[str] = []
    for prefix in SCAN_PREFIXES:
        base = backend / prefix
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            violations.extend(_scan_file(py, backend))

    if violations:
        print("[FAIL] direct os.getenv/os.environ.get in business layers:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("[OK] no direct os.getenv in agents/application/services/api.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
