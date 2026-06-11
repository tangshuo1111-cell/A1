"""Round 5 — application/agents must not direct-import rag/knowledge/storage.knowledge_store."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXCEPTIONS_CSV = PROJECT_ROOT / "docs" / "current" / "migration" / "import_exceptions.csv"


def _grandfathered_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not EXCEPTIONS_CSV.is_file():
        return pairs
    with EXCEPTIONS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            mod = str(row.get("violating_module", "")).strip()
            banned = str(row.get("banned_import", "")).strip()
            if mod and banned:
                pairs.add((mod, banned))
    return pairs


def test_import_boundaries_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_import_boundaries.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_application_chat_kb_paths_use_capability_layer() -> None:
    chat_root = PROJECT_ROOT / "backend" / "application" / "chat"
    kb_pipeline_hits = 0
    direct_rag_hits: list[str] = []
    grandfather = _grandfathered_pairs()
    for path in sorted(chat_root.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT / "backend").as_posix().replace("/", ".")
        text = path.read_text(encoding="utf-8")
        if "services.capabilities.knowledge" in text or "kb_pipeline" in text:
            kb_pipeline_hits += 1
        mod_dotted = rel.replace("/", ".").replace(".py", "")
        for banned in ("from rag.", "import rag.", "from knowledge.", "knowledge_store"):
            if banned not in text:
                continue
            if banned.startswith("from "):
                banned_root = banned.removeprefix("from ").split(".", 1)[0]
            elif banned.startswith("import "):
                banned_root = banned.removeprefix("import ").split(".", 1)[0]
            else:
                banned_root = banned.split(".", 1)[0]
            if (mod_dotted, banned_root) in grandfather:
                continue
            direct_rag_hits.append(f"{rel}: {banned}")
    assert kb_pipeline_hits >= 2
    assert not direct_rag_hits, "direct rag/knowledge imports in application/chat:\n" + "\n".join(direct_rag_hits)
