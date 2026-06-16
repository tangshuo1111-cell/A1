from __future__ import annotations

from pathlib import Path

from scripts.benchmarks.ingest_kb_strengthening_pack import (
    DEFAULT_DOCS,
    DEFAULT_DOCS_ROOT,
    missing_pack_files,
    resolve_docs_root,
)


def test_kb_strengthening_pack_fixtures_present_under_history_current() -> None:
    repo = Path(__file__).resolve().parents[2]
    docs_root = resolve_docs_root(repo, None)
    assert docs_root == repo / DEFAULT_DOCS_ROOT
    missing = missing_pack_files(docs_root)
    assert missing == [], f"missing KB benchmark fixtures: {missing}"
    assert len(DEFAULT_DOCS) == 6
