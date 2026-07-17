"""Unit tests for the AI draft service (fake AI client + seeded index)."""

from __future__ import annotations

from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.services.draft_service import DraftService


class FakeAI:
    model = "claude-test"

    def __init__(self, text_return: str = "Draft reply. The FirstMed Team") -> None:
        self._text = text_return
        self.last_kwargs: dict | None = None

    async def text(self, **kwargs):
        self.last_kwargs = kwargs
        return self._text


async def _seed(db_session):
    repo = DocumentRepository(db_session)
    await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="sop1",
        title="Prescription refill SOP",
        content="Refills are processed within 48 hours by a nurse.",
        url="https://notion.so/sop1",
    )


async def test_generate_with_context_produces_citations(db_session):
    await _seed(db_session)
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Refill request", "Can I get my prescription refilled?", use_context=True
    )

    assert result["draft"].startswith("Draft reply")
    assert result["model"] == "claude-test"
    assert result["requires_human_review"] is True
    assert len(result["citations"]) == 1
    cite = result["citations"][0]
    assert cite["source"] == DocumentSource.notion.value
    assert cite["title"] == "Prescription refill SOP"
    # retrieved content was injected into the prompt
    assert "48 hours" in fake.last_kwargs["user"]


async def test_generate_without_context_has_no_citations(db_session):
    await _seed(db_session)
    fake = FakeAI()
    result = await DraftService(db_session, ai=fake).generate(
        "Refill request", "Refill please", use_context=False
    )
    assert result["citations"] == []
    assert "48 hours" not in fake.last_kwargs["user"]
