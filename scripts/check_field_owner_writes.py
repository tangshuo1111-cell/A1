#!/usr/bin/env python3
"""Scan backend/ for canonical field writes outside owner modules (Round 9).

Usage:
    python scripts/check_field_owner_writes.py [--backend-root backend]

Exit codes:
    0  No violations.
    1  Canonical field write detected outside owner module.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Final writers for canonical top-level response keys.
TOP_LEVEL_OWNERS: dict[str, str] = {
    "task_status": "turn_response_builder.py",
    "primary_path": "turn_response_builder.py",
    "workflow_elapsed_ms": "turn_response_builder.py",
}

# Modules allowed to *construct* pre-exit turn dicts (must use build_chat_turn_result).
PRE_EXIT_BUILDERS = {
    "turn_response_builder.py",
    "fast_delivery.py",
    "build_pending.py",
    "approval_gate_flow.py",
    "complex_executor_exit_extra.py",
    "turn_orchestrator.py",
    "async_executor.py",
}

OWNER_HELPER_BASENAMES = {
    "field_writer.py",
    "exit_extra_builder.py",
}

GRANDFATHER_PATH_FRAGMENTS = (
    "/tests/",
    "\\tests\\",
    "test_",
)


def _grandfathered(path: Path) -> bool:
    s = str(path)
    return any(g in s for g in GRANDFATHER_PATH_FRAGMENTS)


def _scan_file(path: Path) -> list[str]:
    if _grandfathered(path):
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return []

    basename = path.name
    hits: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                self._check(target, node.lineno)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.target is not None:
                self._check(node.target, node.lineno)
            self.generic_visit(node)

        def _check(self, target: ast.AST, lineno: int) -> None:
            if not isinstance(target, ast.Subscript):
                return
            if isinstance(target.value, ast.Name) and target.value.id == "old_for_shadow":
                return
            key = _subscript_key(target)
            if key is None:
                return
            owner = TOP_LEVEL_OWNERS.get(key)
            if owner is None:
                return
            if basename == owner:
                return
            if basename in OWNER_HELPER_BASENAMES:
                return
            if basename == "turn_exit_gate.py":
                return
            # Pre-exit dict assembly is only legal via build_chat_turn_result.
            if key == "workflow_elapsed_ms" and basename in PRE_EXIT_BUILDERS:
                return
            hits.append(f"{path.relative_to(ROOT)}:{lineno}: write to {key!r} outside {owner}")

    def _subscript_key(node: ast.Subscript) -> str | None:
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
        return None

    _Visitor().visit(tree)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Check canonical field owner writes")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend_root = ROOT / args.backend_root
    if not backend_root.is_dir():
        print(f"ERROR: backend root not found: {backend_root}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for py_file in sorted(backend_root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        violations.extend(_scan_file(py_file))

    if violations:
        print("ERROR: canonical field owner violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(f"OK: canonical field writes confined to owners ({len(TOP_LEVEL_OWNERS)} rules).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
