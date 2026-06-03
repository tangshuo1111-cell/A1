"""
Compare KB eval JSON against baseline thresholds (exit 1 on regression).

Usage:
  python scripts/benchmarks/run_kb_agent_eval.py --runner local --output _local/kb_latest.json
  python scripts/benchmarks/check_kb_regression.py --results _local/kb_latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from utf8_console import configure_utf8_stdio  # noqa: E402 - sys.path 注入后才能导入

configure_utf8_stdio()

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIN_V2_KB = 9
DEFAULT_MAX_WEB_FALLBACK = 0


def _primary_path(row: dict) -> str:
    return str(row.get("primary_path") or "")


def _is_v2_kb(path: str) -> bool:
    p = path.lower()
    return "v2_kb" in p or "agno_basic_v2_kb" in p or (p.startswith("kb_") and "fast" not in p)


def _is_web_fallback(path: str) -> bool:
    p = path.lower()
    return "web" in p and ("fallback" in p or "supplement" in p)


def analyze(results: list[dict]) -> dict:
    total = len(results)
    v2_kb = sum(1 for r in results if _is_v2_kb(_primary_path(r)))
    web_fb = sum(1 for r in results if _is_web_fallback(_primary_path(r)))
    ok_rows = sum(1 for r in results if r.get("ok"))
    return {
        "total": total,
        "ok_rows": ok_rows,
        "v2_kb_hits": v2_kb,
        "web_fallback": web_fb,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="KB benchmark regression gate")
    parser.add_argument("--results", required=True, help="JSON array from run_kb_agent_eval.py")
    parser.add_argument("--min-v2-kb", type=int, default=DEFAULT_MIN_V2_KB)
    parser.add_argument("--max-web-fallback", type=int, default=DEFAULT_MAX_WEB_FALLBACK)
    args = parser.parse_args()
    path = Path(args.results)
    results = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise SystemExit("results must be a JSON array")
    stats = analyze(results)
    errors: list[str] = []
    if stats["v2_kb_hits"] < args.min_v2_kb:
        errors.append(f"v2_kb_hits {stats['v2_kb_hits']} < {args.min_v2_kb}")
    if stats["web_fallback"] > args.max_web_fallback:
        errors.append(f"web_fallback {stats['web_fallback']} > {args.max_web_fallback}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if errors:
        for e in errors:
            print(f"REGRESSION: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("KB regression check passed.")


if __name__ == "__main__":
    main()
