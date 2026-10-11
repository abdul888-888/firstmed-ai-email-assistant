"""FirstMed-owned, staff-maintained knowledge-base endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.document import DocumentSource
from app.models.user import User, UserRole
from app.repositories.document import DocumentRepository
from app.schemas.knowledge import KnowledgeEntryList, KnowledgeEntryWrite
from app.schemas.search import DocumentRead

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=KnowledgeEntryList, summary="List FirstMed knowledge entries")
async def list_entries(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KnowledgeEntryList:
    rows = await DocumentRepository(session).list_by_source(DocumentSource.firstmed.value)
    return KnowledgeEntryList(entries=[DocumentRead.model_validate(row) for row in rows], count=len(rows))


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: KnowledgeEntryWrite,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> DocumentRead:
    doc = await DocumentRepository(session).upsert(
        source=DocumentSource.firstmed.value,
        source_id=f"kb-{uuid.uuid4()}",
        title=payload.title.strip(),
        content=payload.content.strip(),
        doc_metadata={"category": payload.category.strip()},
    )
    return DocumentRead.model_validate(doc)


@router.put("/{document_id}", response_model=DocumentRead)
async def update_entry(
    document_id: uuid.UUID,
    payload: KnowledgeEntryWrite,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> DocumentRead:
    repo = DocumentRepository(session)
    doc = await repo.get(document_id)
    if doc is None or doc.source != DocumentSource.firstmed.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    doc.title = payload.title.strip()
    doc.content = payload.content.strip()
    doc.doc_metadata = {"category": payload.category.strip()}
    await session.commit()
    await session.refresh(doc)
    return DocumentRead.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_entry(
    document_id: uuid.UUID,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
) -> Response:
    repo = DocumentRepository(session)
    doc = await repo.get(document_id)
    if doc is None or doc.source != DocumentSource.firstmed.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    await repo.delete(doc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
