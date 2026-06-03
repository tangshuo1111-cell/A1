#!/usr/bin/env python3
"""Enforce import boundary rules for the target architecture.

Rules (from §15.13.1):
  backend.agents.*       must NOT import  backend.rag.*, backend.retrieval.*, backend.knowledge.*
  backend.tools.*        must NOT import  backend.agents.*, backend.application.*
  backend.services.*     must NOT import  backend.agents.*, backend.application.*
  backend.application.*  must NOT import  backend.workers.*, backend.tasks.queue.*
  backend.workers.*      MAY    import    backend.tasks.*, backend.services.*
  backend.api.*          must NOT import  backend.tools.*

Exceptions can be registered in:
  docs/current/migration/import_exceptions.csv  (columns: violating_module, banned_import, reason)

Usage:
    python scripts/check_import_boundaries.py [--backend-root backend]

Exit codes:
    0  No violations.
    1  One or more violations found.
"""
from __future__ import annotations

import argparse
import ast
import csv
import sys
from pathlib import Path
from typing import NamedTuple

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS_CSV = ROOT / "docs" / "current" / "migration" / "import_exceptions.csv"


class Rule(NamedTuple):
    owner_prefix: str
    banned_prefixes: list[str]
    description: str


RULES: list[Rule] = [
    Rule(
        "backend.agents",
        [
            "backend.rag",
            "backend.retrieval",
            "backend.knowledge",
            "rag",
            "retrieval",
            "knowledge",
        ],
        "agents must not directly import rag/retrieval/knowledge; use services.capabilities.knowledge",
    ),
    Rule(
        "backend.tools",
        ["backend.agents", "backend.application"],
        "tools must not import agents or application layers",
    ),
    Rule(
        "backend.services",
        ["backend.agents", "backend.application"],
        "services must not import agents or application layers",
    ),
    Rule(
        "backend.application",
        ["backend.workers", "backend.tasks.queue"],
        "application layer must not import workers or task queues directly",
    ),
    Rule(
        "backend.api",
        ["backend.tools"],
        "api layer must not import tools directly; route through services",
    ),
]


def _load_exceptions() -> set[tuple[str, str]]:
    """Return a set of (violating_module_prefix, banned_import_prefix) exceptions."""
    result: set[tuple[str, str]] = set()
    if not EXCEPTIONS_CSV.exists():
        return result
    with EXCEPTIONS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vm = row.get("violating_module", "").strip()
            bi = row.get("banned_import", "").strip()
            if vm and bi:
                result.add((vm, bi))
    return result


def _module_path_to_dotted(py_file: Path, backend_root: Path) -> str:
    rel = py_file.relative_to(backend_root.parent)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _check_file(
    py_file: Path,
    module_name: str,
    exceptions: set[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            names = [node.module]
        else:
            continue

        for imported in names:
            for rule in RULES:
                if not module_name.startswith(rule.owner_prefix):
                    continue
                for banned in rule.banned_prefixes:
                    if imported.startswith(banned):
                        exc_key = (module_name, banned)
                        exc_key2 = (rule.owner_prefix, banned)
                        if exc_key in exceptions or exc_key2 in exceptions:
                            continue
                        violations.append(
                            f"  {py_file.relative_to(ROOT)}:{node.lineno}  "
                            f"{module_name!r} imports {imported!r}  "
                            f"[{rule.description}]"
                        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Import boundary checker")
    parser.add_argument(
        "--backend-root",
        default="backend",
        help="Relative path to the backend package root (default: backend)",
    )
    args = parser.parse_args()

    backend_root = ROOT / args.backend_root
    if not backend_root.is_dir():
        print(f"ERROR: backend root not found: {backend_root}", file=sys.stderr)
        return 2

    exceptions = _load_exceptions()
    all_violations: list[str] = []

    for py_file in sorted(backend_root.rglob("*.py")):
        module_name = _module_path_to_dotted(py_file, backend_root)
        violations = _check_file(py_file, module_name, exceptions)
        all_violations.extend(violations)

    if all_violations:
        print(
            f"\n[FAIL] {len(all_violations)} import boundary violation(s):\n",
            file=sys.stderr,
        )
        for v in all_violations:
            print(v, file=sys.stderr)
        print(
            "\nTo allow an exception, add a row to "
            "docs/current/migration/import_exceptions.csv",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] No import boundary violations in {backend_root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
