#!/usr/bin/env python3
"""Detect (and optionally fix) stale architecture terms in scoped backend paths.

Replacements (comments / docstrings only when --apply):
  LangGraph          -> turn pipeline
  langgraph          -> turn pipeline
  agno_rag_service   -> retrieve_service
  SQLite FTS5        -> PG tsvector
  SQLite FTS         -> PG knowledge store

Usage:
    python scripts/strip_stale_terms.py [--apply] [--root backend/agents]

Exit codes:
    0  No stale terms (or --apply fixed all).
    1  Stale terms remain.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SCOPES = (
    "backend/application/chat",
    "backend/agents",
    "backend/api/schemas_http.py",
)

REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"LangGraph"), "turn pipeline"),
    (re.compile(r"langgraph"), "turn pipeline"),
    (re.compile(r"agno_rag_service"), "retrieve_service"),
    (re.compile(r"SQLite FTS5"), "PG tsvector"),
    (re.compile(r"SQLite FTS"), "PG knowledge store"),
)

STALE_PATTERN = re.compile(
    r"LangGraph|langgraph|agno_rag_service|SQLite FTS5|SQLite FTS",
    re.IGNORECASE,
)


def _iter_files(scope: Path) -> list[Path]:
    if scope.is_file():
        return [scope]
    return sorted(p for p in scope.rglob("*.py") if p.is_file())


def _check_file(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if STALE_PATTERN.search(line):
            hits.append((lineno, line.strip()))
    return hits


def _apply_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8", errors="replace")
    updated = original
    for pattern, repl in REPLACEMENTS:
        updated = pattern.sub(repl, updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Stale architecture term guard")
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Scope path relative to repo root (repeatable). Default: chat + agents + schemas_http.",
    )
    parser.add_argument("--apply", action="store_true", help="Rewrite matched files in place.")
    args = parser.parse_args()

    scopes = [ROOT / rel for rel in (args.root or list(DEFAULT_SCOPES))]
    failures: list[str] = []

    for scope in scopes:
        if not scope.exists():
            failures.append(f"{scope.relative_to(ROOT)}: scope missing")
            continue
        for py_file in _iter_files(scope):
            rel = py_file.relative_to(ROOT).as_posix()
            if args.apply:
                if _apply_file(py_file):
                    print(f"[APPLY] {rel}")
                continue
            for lineno, snippet in _check_file(py_file):
                failures.append(f"{rel}:{lineno}: {snippet[:120]}")

    if args.apply:
        print("[OK] apply pass complete.")
        return 0

    if failures:
        print(f"\n[FAIL] {len(failures)} stale term(s):\n", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        print("\nRun with --apply to rewrite scoped comments.", file=sys.stderr)
        return 1

    print(f"[OK] no stale terms in {len(scopes)} scope(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
