#!/usr/bin/env python3
"""Guard: security rules must stay centralized in config/safe_rule.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    try:
        from config.safe_rule import SAFE  # noqa: PLC0415
    except ImportError as exc:
        print(f"[FAIL] cannot import config.safe_rule.SAFE: {exc}", file=sys.stderr)
        return 1

    if not getattr(SAFE, "secret_env_prefixes", None):
        print("[FAIL] SAFE.secret_env_prefixes missing", file=sys.stderr)
        return 1
    if not getattr(SAFE, "log_redact_fields", None):
        print("[FAIL] SAFE.log_redact_fields missing", file=sys.stderr)
        return 1

    print("[OK] safe_rule single source (SAFE loaded).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
