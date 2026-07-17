"""Retrieval / search API (Phase 4): search the unified Gmail + Notion index."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.document import DocumentSource
from app.models.user import User
from app.schemas.search import (
    DocumentRead,
    IndexStats,
    ReindexResult,
    SearchHit,
    SearchResponse,
)
from app.services.ingestion_service import IngestionService
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])

_VALID_SOURCES = {s.value for s in DocumentSource}


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {"module": "search", "implemented": True, "phase": 4}


@router.get("", response_model=SearchResponse, summary="Search the retrieval index")
async def search(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    q: str = Query(default="", description="Search text (empty => most recent)"),
    source: list[str] | None = Query(default=None, description="Filter by source(s)"),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    if source:
        invalid = [s for s in source if s not in _VALID_SOURCES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown source(s): {', '.join(invalid)}",
            )

    hits = await SearchService(session).search(q, sources=source, limit=limit)
    results = [
        SearchHit(score=hit.score, document=DocumentRead.model_validate(hit.document))
        for hit in hits
    ]
    return SearchResponse(query=q, count=len(results), results=results)


@router.get("/stats", response_model=IndexStats, summary="Index size per source")
async def stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> IndexStats:
    counts = await SearchService(session).stats()
    return IndexStats(
        total=counts.get("total", 0),
        gmail=counts.get(DocumentSource.gmail.value, 0),
        notion=counts.get(DocumentSource.notion.value, 0),
    )


@router.post(
    "/reindex",
    response_model=ReindexResult,
    summary="Ingest Gmail + Notion content into the index",
)
async def reindex(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ReindexResult:
    result = await IngestionService(session).reindex(current_user)
    return ReindexResult(**result)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentRead,
    summary="Fetch a single indexed document",
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentRead:
    from app.repositories.document import DocumentRepository

    doc = await DocumentRepository(session).get(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentRead.model_validate(doc)
