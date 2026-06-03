"""MiddleAgent must not import rag/retrieval/knowledge directly (§15.10.4)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIDDLE_AGENT_DIR = ROOT / "backend" / "agents" / "middle_agent"
BANNED_PREFIXES = ("rag.", "retrieval.", "knowledge.", "backend.rag.", "backend.retrieval.", "backend.knowledge.")


def _imports_in_file(py_file: Path) -> list[tuple[int, str]]:
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def test_middle_agent_has_no_direct_rag_imports() -> None:
    violations: list[str] = []
    for py_file in sorted(MIDDLE_AGENT_DIR.rglob("*.py")):
        for lineno, module in _imports_in_file(py_file):
            if any(module.startswith(prefix) or module == prefix.rstrip(".") for prefix in BANNED_PREFIXES):
                rel = py_file.relative_to(ROOT)
                violations.append(f"{rel}:{lineno} imports {module!r}")
    assert not violations, "MiddleAgent direct rag/retrieval/knowledge imports:\n" + "\n".join(violations)


def test_middle_agent_uses_knowledge_capability_services() -> None:
    expected_fragments = (
        "services.capabilities.knowledge",
    )
    hits = 0
    for py_file in sorted(MIDDLE_AGENT_DIR.rglob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        if any(fragment in text for fragment in expected_fragments):
            hits += 1
    assert hits >= 4, "expected multiple middle_agent modules wired to knowledge capability services"
