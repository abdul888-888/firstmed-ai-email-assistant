"""Unit tests for ingestion of Gmail + Notion content into the index."""

from __future__ import annotations

from app.models.document import DocumentSource
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.services.gmail_service import GmailNotConnectedError
from app.services.ingestion_service import IngestionService


class FakeGmail:
    def __init__(self, *, connected: bool = True) -> None:
        self.connected = connected

    async def list_messages(self, user, *, max_results=25):
        if not self.connected:
            raise GmailNotConnectedError("not connected")
        return {"messages": [{"id": "m1", "thread_id": "t1"}]}

    async def get_message(self, user, message_id):
        return {
            "id": message_id,
            "thread_id": "t1",
            "subject": "Refill request",
            "from": "patient@example.com",
            "snippet": "Please refill my prescription",
            "date": "2026-01-01",
            "label_ids": ["INBOX"],
        }


class FakeNotion:
    async def search(self, query=None, *, page_size=25):
        return {
            "results": [
                {
                    "id": "p1",
                    "object": "page",
                    "title": "Triage SOP",
                    "url": "https://notion.so/p1",
                    "last_edited_time": "2026-02-01",
                }
            ]
        }

    async def get_page_content(self, page_id, *, page_size=50):
        return {"blocks": [{"text": "Step one"}, {"text": "Step two"}]}


async def _user(db_session) -> User:
    user = User(email="idx@firstmed.com", full_name="Idx")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_ingest_gmail(db_session):
    user = await _user(db_session)
    svc = IngestionService(db_session, gmail=FakeGmail(), notion=FakeNotion())
    n = await svc.ingest_gmail(user)
    assert n == 1

    doc = await DocumentRepository(db_session).get_by_source(DocumentSource.gmail.value, "m1")
    assert doc is not None
    assert doc.title == "Refill request"
    assert "prescription" in doc.content.lower()
    assert doc.doc_metadata["from"] == "patient@example.com"


async def test_ingest_notion_includes_block_text(db_session):
    svc = IngestionService(db_session, gmail=FakeGmail(), notion=FakeNotion())
    n = await svc.ingest_notion()
    assert n == 1

    doc = await DocumentRepository(db_session).get_by_source(DocumentSource.notion.value, "p1")
    assert doc.title == "Triage SOP"
    assert "Step one" in doc.content
    assert "Step two" in doc.content


async def test_ingest_is_idempotent(db_session):
    user = await _user(db_session)
    svc = IngestionService(db_session, gmail=FakeGmail(), notion=FakeNotion())
    await svc.ingest_gmail(user)
    await svc.ingest_gmail(user)  # second pass updates, does not duplicate

    counts = await DocumentRepository(db_session).counts_by_source()
    assert counts[DocumentSource.gmail.value] == 1


async def test_reindex_skips_unavailable_sources(db_session):
    user = await _user(db_session)
    # Gmail not connected and Notion not configured (default empty key).
    svc = IngestionService(db_session, gmail=FakeGmail(connected=False), notion=FakeNotion())
    result = await svc.reindex(user)

    assert result["gmail_indexed"] == 0
    assert result["notion_indexed"] == 0
    assert "gmail: not connected" in result["notes"]
    assert "notion: not configured" in result["notes"]
