#!/usr/bin/env python3
"""Enforce import boundary rules for the target architecture.

Rules (Round 0+):
  backend.agents.*       must NOT import rag/retrieval/knowledge/storage.knowledge_store
  backend.application.*  must NOT import rag/retrieval/knowledge/storage.knowledge_store
                         must NOT import backend.workers.*, backend.tasks.queue.*
  backend.application.*  main path must NOT import backend.compat.*
  backend.agents.*       main path must NOT import backend.compat.*
  backend.api.*          main path must NOT import backend.compat.*
  backend.services.*     main path must NOT import backend.compat.* (service facades stay)
  backend.tools.*        must NOT import backend.agents.*, backend.application.*
  backend.services.*     must NOT import backend.agents.*, backend.application.*
  backend.api.*          must NOT import backend.tools.*

Exceptions: docs/current/migration/import_exceptions.csv
  columns: violating_module, banned_import, reason

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

KNOWLEDGE_BANNED = [
    "backend.rag",
    "backend.retrieval",
    "backend.knowledge",
    "rag",
    "retrieval",
    "knowledge",
    "storage.knowledge_store",
    "backend.storage.knowledge_store",
]

COMPAT_BANNED = ["compat", "backend.compat"]

MAIN_PATH_PREFIXES = (
    "backend.application",
    "backend.agents",
    "backend.api",
    "backend.services",
)

STORAGE_KNOWLEDGE_STORE_SYMBOL = "knowledge_store"


class Rule(NamedTuple):
    owner_prefix: str
    banned_prefixes: list[str]
    description: str
    check_storage_knowledge_store: bool = False


RULES: list[Rule] = [
    Rule(
        "backend.agents",
        KNOWLEDGE_BANNED,
        "agents must not directly import rag/retrieval/knowledge/knowledge_store; "
        "use services.capabilities.knowledge",
        check_storage_knowledge_store=True,
    ),
    Rule(
        "backend.application",
        KNOWLEDGE_BANNED,
        "application must not directly import rag/retrieval/knowledge/knowledge_store; "
        "use services.capabilities.knowledge",
        check_storage_knowledge_store=True,
    ),
    Rule(
        "backend.application",
        ["backend.workers", "backend.tasks.queue"],
        "application layer must not import workers or task queues directly",
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
        "backend.api",
        ["backend.tools"],
        "api layer must not import tools directly; route through services",
    ),
    Rule(
        "backend.application.chat.executors.fast_executor",
        [
            "backend.application.chat.executors.complex_executor",
            "backend.application.chat.executors.async_executor",
        ],
        "fast executor must not import complex/async executors",
    ),
    Rule(
        "backend.application.chat.executors.complex_executor",
        [
            "backend.application.chat.executors.fast_executor",
            "backend.application.chat.executors.async_executor",
        ],
        "complex executor must not import fast/async executors",
    ),
    Rule(
        "backend.application.chat.executors.async_executor",
        [
            "backend.application.chat.executors.fast_executor",
            "backend.application.chat.executors.complex_executor",
        ],
        "async executor must not import fast/complex executors",
    ),
    Rule(
        "backend.agents",
        ["fastapi"],
        "agents must not import FastAPI / HTTP layer",
    ),
]

for _prefix in MAIN_PATH_PREFIXES:
    RULES.append(
        Rule(
            _prefix,
            COMPAT_BANNED,
            f"{_prefix} must not import compat shims; use application/services canonical paths",
        )
    )


def _load_exceptions() -> list[tuple[str, str]]:
    """Return (violating_module_suffix, banned_import_prefix) rows."""
    result: list[tuple[str, str]] = []
    if not EXCEPTIONS_CSV.exists():
        return result
    with EXCEPTIONS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vm = row.get("violating_module", "").strip()
            bi = row.get("banned_import", "").strip()
            if vm and bi:
                result.append((vm, bi))
    return result


def _is_exception(module_name: str, imported: str, exceptions: list[tuple[str, str]]) -> bool:
    for vm_suffix, banned in exceptions:
        if not module_name.endswith(vm_suffix) and vm_suffix not in module_name:
            continue
        if imported == banned or imported.startswith(f"{banned}."):
            return True
    return False


def _module_path_to_dotted(py_file: Path, backend_root: Path) -> str:
    rel = py_file.relative_to(backend_root.parent)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _check_file(
    py_file: Path,
    module_name: str,
    exceptions: list[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                for rule in RULES:
                    if not module_name.startswith(rule.owner_prefix):
                        continue
                    for banned in rule.banned_prefixes:
                        if imported == banned or imported.startswith(f"{banned}."):
                            if _is_exception(module_name, imported, exceptions):
                                continue
                            violations.append(
                                f"  {py_file.relative_to(ROOT)}:{node.lineno}  "
                                f"{module_name!r} imports {imported!r}  "
                                f"[{rule.description}]"
                            )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            imported_mod = node.module
            imported_names = [a.name for a in node.names]
            for rule in RULES:
                if not module_name.startswith(rule.owner_prefix):
                    continue
                for banned in rule.banned_prefixes:
                    if imported_mod == banned or imported_mod.startswith(f"{banned}."):
                        if _is_exception(module_name, imported_mod, exceptions):
                            continue
                        violations.append(
                            f"  {py_file.relative_to(ROOT)}:{node.lineno}  "
                            f"{module_name!r} imports from {imported_mod!r}  "
                            f"[{rule.description}]"
                        )
                if rule.check_storage_knowledge_store and imported_mod == "storage":
                    if STORAGE_KNOWLEDGE_STORE_SYMBOL in imported_names:
                        sym = f"storage.{STORAGE_KNOWLEDGE_STORE_SYMBOL}"
                        if _is_exception(module_name, sym, exceptions):
                            continue
                        violations.append(
                            f"  {py_file.relative_to(ROOT)}:{node.lineno}  "
                            f"{module_name!r} imports {sym!r}  "
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
        if "compat" in py_file.parts or "legacy" in py_file.parts:
            continue
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
            "\nTo allow a grandfathered exception, add a row to "
            "docs/current/migration/import_exceptions.csv",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] No import boundary violations in {backend_root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
