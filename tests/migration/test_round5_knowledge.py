"""Round 5 — unified knowledge retrieve entry."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_retrieve_service_is_canonical_module() -> None:
    path = PROJECT_ROOT / "backend" / "services" / "capabilities" / "knowledge" / "retrieve_service.py"
    text = path.read_text(encoding="utf-8")
    assert "sole business-layer retrieve entry" in text
    assert "def retrieve_knowledge(" in text
    assert "def fetch_knowledge_chunks(" in text


def test_kb_pipeline_delegates_to_retrieve_service() -> None:
    text = (PROJECT_ROOT / "backend" / "services" / "capabilities" / "knowledge" / "kb_pipeline.py").read_text(
        encoding="utf-8"
    )
    assert "retrieve_service.retrieve_knowledge" in text


def test_fast_kb_lane_uses_kb_pipeline() -> None:
    text = (
        PROJECT_ROOT
        / "backend"
        / "application"
        / "chat"
        / "executors"
        / "fast_lanes"
        / "kb_fast_impl.py"
    ).read_text(encoding="utf-8")
    assert "kb_pipeline" in text


def test_shared_material_prep_uses_kb_pipeline() -> None:
    text = (PROJECT_ROOT / "backend" / "application" / "chat" / "shared_material_prep.py").read_text(encoding="utf-8")
    assert "kb_pipeline" in text


def test_legacy_rag_shim_modules_removed_r19() -> None:
    assert not (PROJECT_ROOT / "backend" / "compat" / "rag_service.py").exists()
    assert not (PROJECT_ROOT / "backend" / "knowledge" / "rag_service.py").exists()
