#!/usr/bin/env python3
"""Registry-driven compat/legacy shim consumption guard."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "backend" / "compat" / "compat_shim_registry.json"
BASELINE = ROOT / "tests" / "migration" / "legacy_consumers_baseline.json"
BACKEND = ROOT / "backend"
TESTS = ROOT / "tests"


def _load_registry() -> list[dict[str, object]]:
    return list(json.loads(REGISTRY.read_text(encoding="utf-8")).get("shims") or [])


def _load_baseline() -> dict[str, list[str]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _import_hits(path: Path, modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules:
                    hits.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in modules:
                hits.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
        ):
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value in modules
            ):
                hits.add(first.value)
    return hits


def _iter_python(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def main() -> int:
    records = _load_registry()
    modules = {str(item["module"]) for item in records}
    baseline = _load_baseline()
    failures: list[str] = []

    for item in records:
        module = str(item["module"])
        shim_path = ROOT / str(item["shim_path"])
        status = str(item.get("status") or "").strip().lower()
        if status == "retired":
            if shim_path.is_file():
                failures.append(
                    f"retired shim still present for {module}: {shim_path.relative_to(ROOT)}"
                )
            if baseline.get(module):
                failures.append(
                    f"retired shim still has baseline consumers for {module}: {baseline[module]}"
                )
            continue
        if not shim_path.is_file():
            failures.append(f"missing shim file for {module}: {shim_path.relative_to(ROOT)}")

    for path in _iter_python(BACKEND):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("backend/compat/") or rel in {str(item["shim_path"]) for item in records}:
            continue
        hits = _import_hits(path, modules)
        for hit in sorted(hits):
            failures.append(f"production import forbidden: {rel} -> {hit}")

    observed: dict[str, set[str]] = {module: set() for module in modules}
    for path in _iter_python(TESTS):
        rel = path.relative_to(ROOT).as_posix()
        hits = _import_hits(path, modules)
        for hit in hits:
            observed[hit].add(rel)

    for module in sorted(modules):
        allowed = set(baseline.get(module, []))
        current = observed.get(module, set())
        new_hits = sorted(current - allowed)
        if new_hits:
            failures.append(f"new test consumers for {module}: {', '.join(new_hits)}")

    if failures:
        print("[FAIL] compat consumption violations:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("[OK] compat consumption matches registry/baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
