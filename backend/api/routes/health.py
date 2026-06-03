from __future__ import annotations

import time

from fastapi import APIRouter

from config.settings import settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """存活 + PostgreSQL / 可选 embedding 表探活。"""
    overall = "ok"
    checks: dict[str, object] = {}
    t0 = time.perf_counter()

    try:
        from storage.pg_pool import get_pool

        get_pool()
        with get_pool().connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
        checks["postgresql"] = {
            "status": "ok",
            "configured": True,
            "path": "(DATABASE_URL)",
        }
    except Exception as e:  # noqa: BLE001
        overall = "degraded"
        checks["postgresql"] = {"status": "error", "detail": str(e)[:200]}

    checks["knowledge_db"] = {"status": "skipped", "note": "PostgreSQL 模式（RAG 表）"}
    checks["conversation_db"] = {"status": "skipped", "note": "PostgreSQL 模式（turns）"}
    checks["runtime_db"] = {"status": "skipped", "note": "PostgreSQL 模式（无全局 SQLite runtime）"}

    emb_hint = "disabled"
    if settings.embedding_enabled:
        try:
            from storage.pg_pool import get_pool

            get_pool()
            with get_pool().connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM rag_embeddings;")
                n = cur.fetchone()
                ct = int(n[0]) if n else 0
            emb_hint = "index_present" if ct > 0 else "enabled_no_rows"
        except Exception as e:  # noqa: BLE001
            emb_hint = f"check_failed:{e!s}"[:80]
            overall = "degraded"

    checks["embedding"] = {"mode": emb_hint}

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "status": overall,
        "service": "light_maqa",
        "checks": checks,
        "latency_ms": latency_ms,
    }
