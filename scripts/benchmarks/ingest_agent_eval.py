from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest agent eval artifacts into PG knowledge store.")
    parser.add_argument("--report", required=True, help="Markdown report path")
    parser.add_argument("--json", required=True, help="Scored JSON path")
    parser.add_argument("--benchmark-id", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "backend"))
    from services.capabilities.knowledge.ingest_service import ingest_text

    report_path = Path(args.report)
    json_path = Path(args.json)
    report_text = report_path.read_text(encoding="utf-8")
    json_text = json_path.read_text(encoding="utf-8")

    report_source_id = f"benchmark:{args.benchmark_id}:report"
    json_source_id = f"benchmark:{args.benchmark_id}:scored-json"
    n1 = ingest_text(report_text, source_id=report_source_id)
    n2 = ingest_text(json_text, source_id=json_source_id)
    print(f"{report_source_id} chunks={n1}")
    print(f"{json_source_id} chunks={n2}")


if __name__ == "__main__":
    main()
