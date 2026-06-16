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

# Benchmark fixtures live under docs/history/current (see benchmarks/kb_agent_eval/README.md).
DEFAULT_DOCS_ROOT = Path("docs") / "history" / "current"


def resolve_docs_root(project_root: Path, docs_root: str | None) -> Path:
    if docs_root:
        return Path(docs_root)
    return project_root / DEFAULT_DOCS_ROOT


def missing_pack_files(docs_root: Path) -> list[Path]:
    return [docs_root / name for name in DEFAULT_DOCS if not (docs_root / name).is_file()]


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
        help="Optional docs root. Defaults to docs/history/current (KB benchmark fixtures).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify fixture files exist; do not ingest.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    docs_root = resolve_docs_root(project_root, args.docs_root)
    missing = missing_pack_files(docs_root)
    if missing:
        print("ERROR: KB benchmark strengthening pack incomplete:", file=sys.stderr)
        for path in missing:
            try:
                rel = path.relative_to(project_root)
            except ValueError:
                rel = path
            print(f"  missing: {rel}", file=sys.stderr)
        raise SystemExit(1)

    if args.check_only:
        print(f"OK: {len(DEFAULT_DOCS)} fixture files present under {docs_root.relative_to(project_root)}")
        return

    sys.path.insert(0, str(project_root / "backend"))
    from services.capabilities.knowledge.ingest_service import ingest_text

    for filename in DEFAULT_DOCS:
        path = docs_root / filename
        text = path.read_text(encoding="utf-8")
        source_id = f"benchmark:{args.pack_id}:{path.stem}"
        chunks = ingest_text(text, source_id=source_id)
        print(f"{source_id} chunks={chunks}")


if __name__ == "__main__":
    main()
