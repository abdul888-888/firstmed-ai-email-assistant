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


class FakeNotionWithDatabase:
    """Search returns a database object; query_database returns pricing rows."""

    async def search(self, query=None, *, page_size=25):
        return {
            "results": [
                {
                    "id": "db-pricing",
                    "object": "database",
                    "title": "Service Pricing",
                    "url": "https://notion.so/db-pricing",
                    "last_edited_time": "2026-03-01",
                }
            ]
        }

    async def query_database(self, database_id, *, page_size=100):
        assert database_id == "db-pricing"
        return {
            "results": [
                {
                    "id": "row-mri",
                    "object": "page",
                    "title": "MRI Scan",
                    "url": "https://notion.so/row-mri",
                    "last_edited_time": "2026-03-01",
                    "properties": {"Service": "MRI Scan", "Self-Pay Price": "$650"},
                    "content": "Service: MRI Scan\nSelf-Pay Price: $650",
                },
                {
                    "id": "row-consult",
                    "object": "page",
                    "title": "Consultation",
                    "url": "https://notion.so/row-consult",
                    "last_edited_time": "2026-03-01",
                    "properties": {"Service": "Consultation", "Self-Pay Price": "$120"},
                    "content": "Service: Consultation\nSelf-Pay Price: $120",
                },
            ]
        }


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


async def test_ingest_notion_expands_database_rows_with_prices(db_session):
    # The core Bug-2 fix: a Notion database is expanded into per-row documents
    # whose property values (prices) are captured — not just the database title.
    svc = IngestionService(
        db_session, gmail=FakeGmail(), notion=FakeNotionWithDatabase()
    )
    n = await svc.ingest_notion()
    assert n == 2  # two rows, indexed individually

    repo = DocumentRepository(db_session)
    mri = await repo.get_by_source(DocumentSource.notion.value, "row-mri")
    assert mri is not None
    assert mri.title == "MRI Scan"
    assert "$650" in mri.content  # the price is now retrievable content
    assert mri.doc_metadata["object"] == "database_row"
    assert mri.doc_metadata["database_title"] == "Service Pricing"

    consult = await repo.get_by_source(DocumentSource.notion.value, "row-consult")
    assert "$120" in consult.content


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
