"""Unit tests for lexical search ranking + tokenization."""

from __future__ import annotations

from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.services.search_service import SearchService, tokenize


def test_tokenize_dedups_and_lowercases():
    assert tokenize("Refill  refill PRESCRIPTION!") == ["refill", "prescription"]


async def _seed(db_session):
    repo = DocumentRepository(db_session)
    await repo.upsert(
        source=DocumentSource.gmail.value,
        source_id="g1",
        title="Prescription refill request",
        content="Patient asks about prescription refill and dosage",
    )
    await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="n1",
        title="Billing FAQ",
        content="How to handle invoice and billing questions",
    )
    await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="n2",
        title="Appointment scheduling SOP",
        content="Steps to schedule an appointment; mentions prescription once",
    )


async def test_search_ranks_title_matches_higher(db_session):
    await _seed(db_session)
    hits = await SearchService(db_session).search("prescription")
    # Both g1 (title+body) and n2 (body only) match; g1 must rank first.
    assert [h.document.source_id for h in hits] == ["g1", "n2"]
    assert hits[0].score > hits[1].score


async def test_search_source_filter(db_session):
    await _seed(db_session)
    hits = await SearchService(db_session).search(
        "prescription", sources=[DocumentSource.notion.value]
    )
    assert [h.document.source_id for h in hits] == ["n2"]


async def test_search_no_terms_returns_recent(db_session):
    await _seed(db_session)
    hits = await SearchService(db_session).search("", limit=2)
    assert len(hits) == 2  # browse mode, most-recent first


async def test_search_no_matches(db_session):
    await _seed(db_session)
    hits = await SearchService(db_session).search("radiology")
    assert hits == []


async def test_stats(db_session):
    await _seed(db_session)
    stats = await SearchService(db_session).stats()
    assert stats["total"] == 3
    assert stats[DocumentSource.gmail.value] == 1
    assert stats[DocumentSource.notion.value] == 2
