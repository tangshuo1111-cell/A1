#!/usr/bin/env python3
"""Guard: test/smoke paths must not hardcode the production database name.

Production DB name: ``light_maqa`` (no suffix).
Allowed test DB names must end with ``_sandbox``, ``_test``, or ``_ci``.

CI workflows (``.github/workflows/``) may reference ephemeral ``light_maqa`` — excluded.
``docker-compose.yml`` defines production — excluded.

Usage:
    python scripts/check_test_db_isolation.py

Exit codes:
    0  No violations.
    1  Hardcoded production DB URL found in guarded paths.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths scanned for hardcoded production DB references.
GUARDED_GLOBS = (
    "tests/smoke/**/*.py",
    "tests/evaluation/**/*.py",
    "tests/evaluation/**/*.yaml",
    "scripts/evaluation/**/*.py",
    "scripts/run_metrics_sandbox*.py",
    "scripts/run_metrics_sandbox*.ps1",
    "scripts/metrics_sandbox_samples.yaml",
)

# Never scan these (production definition / CI ephemeral injection).
SKIP_PREFIXES = (
    ".github/",
    "docker-compose.yml",
    "docker-compose.metrics-sandbox.yml",
)

# Allowed DB name suffixes when hardcoded in guarded paths.
_ALLOWED_SUFFIXES = ("_sandbox", "_test", "_ci")

# Matches ``/light_maqa`` as a path segment (not ``light_maqa_metrics_sandbox`` etc.).
_PROD_DB_SEGMENT = re.compile(
    r"/light_maqa(?![\w_])(?:[\"'\s\?\)]|$)",
    re.IGNORECASE,
)


def _is_skipped(rel: str) -> bool:
    return any(rel.replace("\\", "/").startswith(p) for p in SKIP_PREFIXES)


def _iter_guarded_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in GUARDED_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if _is_skipped(rel):
                continue
            if path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def _line_has_prod_db(line: str) -> bool:
    if "light_maqa" not in line.lower():
        return False
    for suffix in _ALLOWED_SUFFIXES:
        if f"light_maqa{suffix}" in line.lower():
            return False
    return bool(_PROD_DB_SEGMENT.search(line))


def main() -> int:
    violations: list[str] = []

    for path in _iter_guarded_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(f"{rel}: cannot read ({exc})")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _line_has_prod_db(line):
                violations.append(f"{rel}:{lineno}: hardcoded production DB name `light_maqa`")

    if violations:
        print("[FAIL] test/smoke DB isolation violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nUse an isolated DB (e.g. light_maqa_metrics_sandbox) or read DATABASE_URL from env.",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] test/smoke DB isolation ({len(_iter_guarded_files())} guarded files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
