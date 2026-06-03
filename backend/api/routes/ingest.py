from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import verify_admin_optional
from api.schemas_http import IngestPathsRequest, IngestResponse, IngestTextRequest
from config.settings import settings
from services.capabilities.knowledge import ingest_service

router = APIRouter(dependencies=[Depends(verify_admin_optional)])


class SamplesResponse(BaseModel):
    ok: bool = True
    chunks_written: int = 0
    note: str = Field(default="ingested knowledge_samples/")


@router.post("/samples", response_model=SamplesResponse)
def ingest_samples() -> SamplesResponse:
    n = ingest_service.ingest_knowledge_samples_dir()
    return SamplesResponse(chunks_written=n)


@router.post("/paths", response_model=IngestResponse)
def ingest_paths(body: IngestPathsRequest) -> IngestResponse:
    paths = []
    for p in body.paths:
        pp = Path(p)
        if not pp.is_absolute():
            pp = settings.project_root / pp
        paths.append(pp)
    n = ingest_service.ingest_paths(paths)
    return IngestResponse(chunks_written=n)


@router.post("/text", response_model=IngestResponse)
def ingest_text(body: IngestTextRequest) -> IngestResponse:
    n = ingest_service.ingest_text(body.text, body.source_id)
    return IngestResponse(chunks_written=n)
