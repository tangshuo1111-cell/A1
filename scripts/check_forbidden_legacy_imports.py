#!/usr/bin/env python3
"""Block new imports of legacy paths marked forbidden_new_import=1.

Reads: docs/current/migration/legacy_paths_status.csv
Grandfathered imports: docs/current/migration/import_exceptions.csv

Usage:
    python scripts/check_forbidden_legacy_imports.py [--backend-root backend]

Exit codes:
    0  No forbidden legacy imports outside exceptions.
    1  Violations found.
"""

from __future__ import annotations

import argparse
import ast
import csv
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
LEGACY_CSV = ROOT / "docs" / "current" / "migration" / "legacy_paths_status.csv"
EXCEPTIONS_CSV = ROOT / "docs" / "current" / "migration" / "import_exceptions.csv"


def _load_forbidden_paths() -> list[str]:
    if not LEGACY_CSV.exists():
        return []
    forbidden: list[str] = []
    with LEGACY_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("forbidden_new_import", "").strip() != "1":
                continue
            legacy = row.get("legacy_path", "").strip()
            if not legacy or legacy.endswith(".py"):
                path = legacy.replace("/", ".").replace("\\", ".")
                if path.startswith("backend."):
                    path = path[len("backend.") :]
                forbidden.append(path)
            elif ":" in legacy:
                mod, _sym = legacy.split(":", 1)
                forbidden.append(mod.replace("/", ".").replace("\\", "."))
    return forbidden


def _load_exceptions() -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if not EXCEPTIONS_CSV.exists():
        return result
    with EXCEPTIONS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vm = row.get("violating_module", "").strip()
            bi = row.get("banned_import", "").strip()
            if vm and bi:
                result.append((vm, bi))
    return result


def _module_name(py_file: Path, backend_root: Path) -> str:
    rel = py_file.relative_to(backend_root.parent)
    return ".".join(rel.with_suffix("").parts)


def _matches_forbidden(imported: str, forbidden_paths: list[str]) -> str | None:
    for legacy in forbidden_paths:
        dotted = legacy.replace("/", ".")
        if imported == dotted or imported.startswith(f"{dotted}."):
            return legacy
        # file path style -> module
        if imported.replace(".", "/") == legacy:
            return legacy
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Forbidden legacy import checker")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend_root = ROOT / args.backend_root
    forbidden_paths = _load_forbidden_paths()
    exceptions = _load_exceptions()
    violations: list[str] = []

    for py_file in sorted(backend_root.rglob("*.py")):
        if "compat" in py_file.parts or "legacy" in py_file.parts or "tests" in py_file.parts:
            continue
        module_name = _module_name(py_file, backend_root)
        try:
            tree = ast.parse(
                py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file)
            )
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            imports: list[tuple[int, str]] = []
            if isinstance(node, ast.Import):
                imports = [(node.lineno, alias.name) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [(node.lineno, node.module)]
            for lineno, imported in imports:
                hit = _matches_forbidden(imported, forbidden_paths)
                if not hit:
                    continue
                exc_used = any(
                    (module_name.endswith(vm) or vm in module_name)
                    and (imported == bi or imported.startswith(f"{bi}."))
                    for vm, bi in exceptions
                )
                if exc_used:
                    continue
                violations.append(
                    f"  {py_file.relative_to(ROOT)}:{lineno}  "
                    f"imports {imported!r}  [forbidden legacy: {hit}]"
                )

    if violations:
        print(f"\n[FAIL] {len(violations)} forbidden legacy import(s):\n", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        return 1

    print("[OK] No forbidden legacy imports outside registered exceptions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
