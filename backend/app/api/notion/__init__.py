"""Notion integration API (Phase 3): read access to the knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.notion import (
    NotionConnection,
    NotionPage,
    NotionPageContent,
    NotionSearchResults,
)
from app.services.notion_service import (
    NotionApiError,
    NotionNotConfiguredError,
    NotionService,
)

router = APIRouter(prefix="/notion", tags=["notion"])

_NOT_CONFIGURED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Notion integration is not configured on this server",
)


def _api_error(exc: NotionApiError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Notion API error")


@router.get("/status", summary="Module status")
async def status_() -> dict:
    return {"module": "notion", "implemented": True, "phase": 3}


@router.get(
    "/connection",
    response_model=NotionConnection,
    summary="Whether the Notion integration is configured",
)
async def connection(current_user: User = Depends(get_current_user)) -> NotionConnection:
    try:
        data = await NotionService().get_connection()
    except NotionApiError as exc:
        raise _api_error(exc) from exc
    return NotionConnection(**data)


@router.get(
    "/search",
    response_model=NotionSearchResults,
    summary="Search pages and databases the integration can see",
)
async def search(
    current_user: User = Depends(get_current_user),
    q: str | None = Query(default=None, description="Search text"),
    page_size: int = Query(default=25, ge=1, le=100),
) -> NotionSearchResults:
    try:
        data = await NotionService().search(q, page_size=page_size)
    except NotionNotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except NotionApiError as exc:
        raise _api_error(exc) from exc
    return NotionSearchResults(**data)


@router.get(
    "/pages/{page_id}",
    response_model=NotionPage,
    summary="Retrieve a page's metadata + properties",
)
async def get_page(
    page_id: str,
    current_user: User = Depends(get_current_user),
) -> NotionPage:
    try:
        data = await NotionService().get_page(page_id)
    except NotionNotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except NotionApiError as exc:
        raise _api_error(exc) from exc
    return NotionPage(**data)


@router.get(
    "/pages/{page_id}/content",
    response_model=NotionPageContent,
    summary="Read a page's child blocks as text",
)
async def get_page_content(
    page_id: str,
    current_user: User = Depends(get_current_user),
    page_size: int = Query(default=50, ge=1, le=100),
) -> NotionPageContent:
    try:
        data = await NotionService().get_page_content(page_id, page_size=page_size)
    except NotionNotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except NotionApiError as exc:
        raise _api_error(exc) from exc
    return NotionPageContent(**data)


@router.get(
    "/databases/{database_id}/query",
    response_model=NotionSearchResults,
    summary="Query a database's rows",
)
async def query_database(
    database_id: str,
    current_user: User = Depends(get_current_user),
    page_size: int = Query(default=25, ge=1, le=100),
) -> NotionSearchResults:
    try:
        data = await NotionService().query_database(database_id, page_size=page_size)
    except NotionNotConfiguredError as exc:
        raise _NOT_CONFIGURED from exc
    except NotionApiError as exc:
        raise _api_error(exc) from exc
    return NotionSearchResults(**data)
