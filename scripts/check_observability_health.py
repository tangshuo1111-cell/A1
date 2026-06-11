#!/usr/bin/env python3
"""Evaluate observability alert rules against in-process metrics snapshot (R21)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
RULES = ROOT / "docs" / "current" / "observability" / "alert_rules.yaml"
DASHBOARD = ROOT / "docs" / "current" / "observability" / "dashboard_panels.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _counter_value(counters: dict[str, int | float], name: str) -> float:
    return float(counters.get(name, 0))


def _eval_expr(expr: str, counters: dict[str, int | float]) -> float:
    import re

    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", expr))
    reserved = {"max"}
    safe = {name: _counter_value(counters, name) for name in tokens if name not in reserved}
    safe["max"] = max
    return float(eval(expr, {"__builtins__": {}}, safe))  # noqa: S307 — trusted rules file


def main() -> int:
    if not RULES.is_file():
        print(f"ERROR: missing {RULES}", file=sys.stderr)
        return 2
    if not DASHBOARD.is_file():
        print(f"ERROR: missing {DASHBOARD}", file=sys.stderr)
        return 2

    from observability import metrics_snapshot

    snap = metrics_snapshot()
    counters = dict(snap.get("counters") or {})
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}
    fired: list[str] = []

    for rule in rules.get("alerts") or []:
        value = _eval_expr(str(rule["expr"]), counters)
        threshold = float(rule["threshold"])
        if value >= threshold:
            fired.append(f"{rule['id']} ({rule['severity']}): {value} >= {threshold}")

    scrape_example = ROOT / "docs" / "current" / "observability" / "prometheus_scrape.example.yml"
    if not scrape_example.is_file():
        print(f"ERROR: missing {scrape_example}", file=sys.stderr)
        return 2

    if fired:
        print("[ALERT] observability rules fired:")
        for item in fired:
            print(f"  - {item}")
        return 1

    print("[OK] observability metrics healthy (no alert rules fired).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
