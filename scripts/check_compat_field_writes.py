#!/usr/bin/env python3
"""Scan backend/ for writes to compat fields marked retired in compat_retirement.csv.

Usage:
    python scripts/check_compat_field_writes.py [--backend-root backend]

Exit codes:
    0  No forbidden writes (or no retired field rules yet).
    1  One or more writes to retired fields detected.
"""
from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPAT_CSV = ROOT / "docs" / "current" / "migration" / "compat_retirement.csv"

# Match subscript/string keys: extra["video_task_id"], extra['video_task_id']
_SUBSCRIPT_RE = re.compile(
    r"""^\s*(?:extra|result\.extra|payload\.extra)\[\s*['"]([^'"]+)['"]\s*\]\s*=""",
    re.MULTILINE,
)
# Match dict literal keys in assignments: {"video_task_id": ...}
_DICT_KEY_RE = re.compile(
    r"""['"]([^'"]+)['"]\s*:""",
)


def _load_retired_field_ids() -> set[str]:
    if not COMPAT_CSV.exists():
        return set()
    retired: set[str] = set()
    with COMPAT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("item_type", "").strip() != "field_mirror":
                continue
            if row.get("status", "").strip() != "retired":
                continue
            item_id = row.get("item_id", "").strip()
            if not item_id:
                continue
            # extra.video_task_id -> video_task_id
            if item_id.startswith("extra."):
                retired.add(item_id.split(".", 1)[1])
            else:
                retired.add(item_id)
    return retired


def _scan_file(path: Path, retired_fields: set[str]) -> list[tuple[int, str, str]]:
    if not retired_fields:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    hits: list[tuple[int, str, str]] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    class _Writer(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                self._check_target(target, node.lineno)
            self.generic_visit(node)

        def _check_target(self, node: ast.AST, lineno: int) -> None:
            if isinstance(node, ast.Subscript):
                key = _subscript_key(node)
                if key in retired_fields:
                    hits.append((lineno, key, "subscript_assign"))
            elif isinstance(node, ast.Attribute):
                if node.attr in retired_fields:
                    hits.append((lineno, node.attr, "attribute_assign"))

        def visit_AugAssign(self, node: ast.AugAssign) -> None:
            self._check_target(node.target, node.lineno)
            self.generic_visit(node)

    def _subscript_key(node: ast.Subscript) -> str | None:
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
        return None

    _Writer().visit(tree)

    # Fallback regex for patterns AST may miss (e.g. multi-line dict spreads)
    for match in _SUBSCRIPT_RE.finditer(source):
        field = match.group(1)
        if field in retired_fields:
            lineno = source[: match.start()].count("\n") + 1
            hits.append((lineno, field, "regex_subscript_assign"))

    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Check retired compat field writes")
    parser.add_argument(
        "--backend-root",
        default="backend",
        help="Backend root relative to project root (default: backend)",
    )
    args = parser.parse_args()

    retired_fields = _load_retired_field_ids()
    if not retired_fields:
        print("OK: no retired field_mirror rules; nothing to scan.")
        return 0

    backend_root = ROOT / args.backend_root
    if not backend_root.is_dir():
        print(f"ERROR: backend root not found: {backend_root}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for py_file in sorted(backend_root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        for lineno, field, kind in _scan_file(py_file, retired_fields):
            rel = py_file.relative_to(ROOT)
            violations.append(f"{rel}:{lineno}: write to retired field {field!r} ({kind})")

    if violations:
        print("ERROR: retired compat field writes detected:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(f"OK: no writes to {len(retired_fields)} retired field(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
