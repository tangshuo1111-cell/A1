# Knowledge Capability Plane

Unified orchestration entry for KB retrieve / rerank / grounding / pending schema.

MiddleAgent and application layers must import from this package only — not `rag.*`, `retrieval.*`, or `knowledge.*` directly.

**Sole business retrieve answer:** `retrieve_service.retrieve_knowledge` (or `kb_pipeline` which delegates to it).

| Module | Role |
|---|---|
| `retrieve_service.py` | **canonical** `retrieve_knowledge`, `fetch_knowledge_chunks`, `search_kb`, `count_kb_chunks` |
| `rerank_service.py` | score-based chunk reorder |
| `grounding_service.py` | context block assembly + RAG marker cleanup |
| `pending_service.py` | pending lifecycle types/constants |
| `pending_ingestion_service.py` | prepare/commit operations |
| `ingest_service.py` | document ingest |
| `kb_pipeline.py` | retrieve → rerank → grounding 统一 fast/complex 入口 |
| `rag_orchestration_service.py` | high-level RAG block fetch for fast/complex lanes |
