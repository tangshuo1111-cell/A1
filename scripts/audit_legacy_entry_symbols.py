#!/usr/bin/env python3
"""Audit canonical chat execution modules and legacy entry import sites (Cleanup C0+).

Legacy entry shells (fast_path_entry / complex_path_entry / async_entry) were removed
in Cleanup C6. This script reports canonical replacements and any remaining references.

Usage:
    python scripts/audit_legacy_entry_symbols.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

RETIRED_ENTRIES = (
    "application.chat.fast_path_entry",
    "application.chat.complex_path_entry",
    "application.chat.async_entry",
)

CANONICAL_MODULES = (
    ("executors/fast_lanes/fast_common.py", "application.chat.executors.fast_lanes.fast_common"),
    ("executors/fast_lanes/kb_fast_impl.py", "application.chat.executors.fast_lanes.kb_fast_impl"),
    ("executors/fast_delivery.py", "application.chat.executors.fast_delivery"),
    ("executors/complex/complex_path_impl.py", "application.chat.executors.complex.complex_path_impl"),
    ("executors/complex/complex_feedback_impl.py", "application.chat.executors.complex.complex_feedback_impl"),
    ("executors/complex/complex_multisource_impl.py", "application.chat.executors.complex.complex_multisource_impl"),
    ("executors/async_path/build_pending.py", "application.chat.executors.async_path.build_pending"),
)


def _public_defs(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _importers(module: str, *, skip_path: Path | None = None) -> list[str]:
    hits: list[str] = []
    for py in BACKEND.rglob("*.py"):
        if skip_path is not None and py.resolve() == skip_path.resolve():
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == module:
                hits.append(py.relative_to(ROOT).as_posix())
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == module:
                        hits.append(py.relative_to(ROOT).as_posix())
    return sorted(set(hits))


def _legacy_text_references() -> list[str]:
    hits: list[str] = []
    needles = tuple(m.split(".")[-1] for m in RETIRED_ENTRIES)
    for py in BACKEND.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        text = py.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                hits.append(f"{rel}: mentions {needle}")
                break
    return sorted(set(hits))


def main() -> int:
    print("== Retired legacy entry shells (Cleanup C6) ==")
    for mod in RETIRED_ENTRIES:
        name = mod.rsplit(".", 1)[-1] + ".py"
        path = BACKEND / "application" / "chat" / name
        status = "DELETED (expected)" if not path.is_file() else f"STILL PRESENT ({path})"
        print(f"  {mod}: {status}")

    print("\n== Canonical execution modules ==")
    for rel, mod in CANONICAL_MODULES:
        path = BACKEND / "application" / "chat" / rel
        if not path.is_file():
            print(f"\n== {rel}: MISSING ==")
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        public = _public_defs(path)
        importers = _importers(mod, skip_path=path)
        print(f"\n== {rel} ({lines} lines) ==")
        print("module:", mod)
        print("public:", ", ".join(public[:12]) + (" ..." if len(public) > 12 else "") if public else "(none)")
        print("importers:", len(importers))
        for item in importers[:15]:
            print(f"  - {item}")
        if len(importers) > 15:
            print(f"  ... +{len(importers) - 15} more")

    print("\n== Legacy entry name references in backend/*.py (should trend to 0) ==")
    refs = _legacy_text_references()
    print(f"files mentioning legacy entry names: {len(refs)}")
    for item in refs[:25]:
        print(f"  - {item}")
    if len(refs) > 25:
        print(f"  ... +{len(refs) - 25} more")

    for mod in RETIRED_ENTRIES:
        importers = _importers(mod)
        if importers:
            print(f"\n[WARN] direct imports of {mod}:", file=sys.stderr)
            for item in importers:
                print(f"  {item}", file=sys.stderr)
            return 1

    print("\n[OK] no direct imports of retired legacy entry modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
