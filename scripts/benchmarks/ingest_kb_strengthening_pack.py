from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_DOCS = [
    "20_KB补强_主链边界与复杂题升级规则.md",
    "21_KB补强_材料流与不依赖后台TaskJoin原则.md",
    "22_KB补强_当前系统风险优先级与四周整改路线图.md",
    "23_KB补强_重视频Compare信息流与专项链协作.md",
    "24_KB补强_基准题直答材料_A.md",
    "25_KB补强_基准题直答材料_B.md",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest the KB benchmark strengthening document pack into PG knowledge store."
    )
    parser.add_argument(
        "--pack-id",
        default="kb-benchmark-strengthening-2026-05-27-a",
        help="Stable pack id used to build source_ids.",
    )
    parser.add_argument(
        "--docs-root",
        default=None,
        help="Optional docs/current root. Defaults to project docs/current.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "backend"))
    from services.capabilities.knowledge.ingest_service import ingest_text

    docs_root = Path(args.docs_root) if args.docs_root else project_root / "docs" / "current"

    for filename in DEFAULT_DOCS:
        path = docs_root / filename
        text = path.read_text(encoding="utf-8")
        source_id = f"benchmark:{args.pack_id}:{path.stem}"
        chunks = ingest_text(text, source_id=source_id)
        print(f"{source_id} chunks={chunks}")


if __name__ == "__main__":
    main()
