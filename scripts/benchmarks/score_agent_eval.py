from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from utf8_console import configure_utf8_stdio  # noqa: E402 - sys.path 注入后才能导入

configure_utf8_stdio()


def load_results(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "total": len(results),
        "http_500": 0,
        "non_json": 0,
        "fast": 0,
        "complex": 0,
        "unknown_mode": 0,
    }
    for item in results:
        if int(item.get("http_status") or 0) >= 500:
            counts["http_500"] += 1
        if "answer" not in item and "raw_text" in item:
            counts["non_json"] += 1
        mode = ((item.get("extra") or {}).get("mode") if isinstance(item.get("extra"), dict) else None)
        if mode == "fast":
            counts["fast"] += 1
        elif mode == "complex":
            counts["complex"] += 1
        else:
            counts["unknown_mode"] += 1
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize an agent eval raw result file.")
    parser.add_argument("results")
    parser.add_argument("--output", default="")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    results_path = Path(args.results)
    results = load_results(results_path)
    payload = {
        "source_results": str(results_path),
        "summary": summarize(results),
        "items": results,
    }
    output = Path(args.output) if args.output else results_path.with_name(results_path.stem + ".summary.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
