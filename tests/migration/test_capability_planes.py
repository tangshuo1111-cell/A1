"""P7/P9 capability plane structure and wiring acceptance."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES = ROOT / "backend" / "services" / "capabilities"


def test_document_capability_plane_modules_exist() -> None:
    document_dir = CAPABILITIES / "document"
    required = (
        "parse_service.py",
        "ocr_service.py",
        "summarize_service.py",
        "early_document_support.py",
        "async_document_pipeline.py",
        "README.md",
    )
    missing = [name for name in required if not (document_dir / name).is_file()]
    assert not missing, f"missing document capability modules: {missing}"


def test_knowledge_capability_plane_modules_exist() -> None:
    knowledge_dir = CAPABILITIES / "knowledge"
    required = (
        "retrieve_service.py",
        "rerank_service.py",
        "grounding_service.py",
        "pending_service.py",
        "kb_pipeline.py",
        "README.md",
    )
    missing = [name for name in required if not (knowledge_dir / name).is_file()]
    assert not missing, f"missing knowledge capability modules: {missing}"


def test_kb_pipeline_exports_unified_capabilities() -> None:
    from services.capabilities.knowledge.kb_pipeline import (
        KB_FAST_CAPABILITIES,
        fetch_kb_answer_material,
    )

    assert "capability.kb.retrieve" in KB_FAST_CAPABILITIES
    assert "capability.kb.rerank" in KB_FAST_CAPABILITIES
    assert "capability.kb.grounding" in KB_FAST_CAPABILITIES
    assert callable(fetch_kb_answer_material)


def test_document_parse_service_resolves_tools() -> None:
    from services.capabilities.document.parse_service import resolve_tool_for_path

    assert resolve_tool_for_path("sample.pdf") == "parse_pdf"
    assert resolve_tool_for_path("notes.txt") == "parse_txt_document"
