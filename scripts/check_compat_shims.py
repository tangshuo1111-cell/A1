#!/usr/bin/env python3
"""Verify compat shim modules carry DEPRECATED_COMPAT_SHIM marker (Round 10).

Usage:
    python scripts/check_compat_shims.py [--backend-root backend]

Exit codes:
    0  All required shims marked.
    1  Missing marker or unknown compat module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "DEPRECATED_COMPAT_SHIM"
REGISTRY = ROOT / "backend" / "compat" / "compat_shim_registry.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compat shim marker checker")
    parser.add_argument("--backend-root", default="backend")
    args = parser.parse_args()

    backend = ROOT / args.backend_root
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    required_compat_modules = tuple(registry.get("core_modules") or ())
    required_shim_surfaces = tuple(registry.get("surface_shims") or ())
    violations: list[str] = []

    for rel in required_compat_modules + required_shim_surfaces:
        path = backend / rel.replace("/", "\\") if False else backend / Path(rel)
        if not path.is_file():
            violations.append(f"missing shim file: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in text:
            violations.append(f"{rel}: missing {MARKER!r} marker")

    compat_dir = backend / "compat"
    if compat_dir.is_dir():
        for py in sorted(compat_dir.rglob("*.py")):
            if py.name == "__init__.py":
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if MARKER not in text:
                violations.append(f"{py.relative_to(backend)}: missing {MARKER!r}")

    if violations:
        print("[FAIL] compat shim marker violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(f"[OK] compat shims marked ({len(required_compat_modules)} core + surfaces).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
