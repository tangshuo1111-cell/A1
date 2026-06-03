"""Knowledge index / ingest bridge."""

from backend.knowledge.ingest_service import (
    ingest_knowledge_samples_dir,
    ingest_paths,
    ingest_text,
)
from rag.ingest import ingest_documents
from rag.video_ingest import ingest_video_bundle

__all__ = [
    "ingest_documents",
    "ingest_knowledge_samples_dir",
    "ingest_paths",
    "ingest_text",
    "ingest_video_bundle",
]
