from __future__ import annotations

from backend.knowledge.ingest_service import ingest_knowledge_samples_dir


def main() -> int:
    chunks = ingest_knowledge_samples_dir()
    print(f"ingested sample chunks={chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
