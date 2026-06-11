#!/usr/bin/env python3
"""Block direct test patching of internal *_impl symbols.

Tests should patch stable use points or canonical service modules instead of
reaching into implementation-only `*_impl.py` internals.
"""

from __future__ import annotations

import ast
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = ROOT / "tests"


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _patched_target(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _is_patch_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "patch"
    if isinstance(func, ast.Attribute):
        return func.attr == "setattr"
    return False


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for path in _iter_python_files(TESTS_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_patch_call(node):
                continue
            target = _patched_target(node)
            if target and "_impl." in target:
                violations.append((str(path.relative_to(ROOT)), node.lineno, target))

    if violations:
        print("[FAIL] direct *_impl patch targets are not allowed:")
        for rel, lineno, target in violations:
            print(f"  - {rel}:{lineno} -> {target}")
        return 1

    print("[OK] no direct *_impl patch targets found in tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
