"""Verification: does Notion-sourced content flow through the pgvector pipeline?

Findings (see module docstrings in ``app/services/notion_service.py`` and
``app/models/template.py`` for the underlying code):

1. There is no live Notion -> database sync job. ``NotionService`` is a
   read-only browse API called on demand from ``/api/v1/notion/*``; it never
   writes to ``documents`` or ``templates``. The only thing that populates
   Notion-tagged rows today is ``scripts/seed_demo.py``, which upserts
   hardcoded Python strings tagged ``source="notion"`` — not a live API pull.
2. Only ``Document`` rows participate in the Phase 9 embedding pipeline.
   ``Template`` (the canned-response snippets Notion content would map to)
   has **no embedding column at all** — see ``test_templates_have_no_embedding_column``
   below, which pins this down as an executable fact rather than a claim.
3. What *does* work, and is verified here: once Notion-sourced content is
   upserted into ``documents`` (by whatever means), ``EmbeddingService.backfill()``
   embeds it through the same ``PortableVector`` column used for every other
   source — a native pgvector ``Vector`` on PostgreSQL, a JSON array fallback
   on SQLite. There is nothing Notion-specific about the vector format itself.
"""

from __future__ import annotations

from app.models.document import DocumentSource
from app.models.template import Template
from app.repositories.document import DocumentRepository
from app.services.embedding_service import EmbeddingService


class FakeEmbedder:
    model = "fake-notion-verify"

    async def embed_documents(self, texts):
        return [[float(len(t)), 0.0, 1.0] for t in texts]

    async def embed_query(self, text):
        return [float(len(text)), 0.0, 1.0]


async def test_notion_sourced_documents_get_embedded_via_pgvector_pipeline(db_session):
    repo = DocumentRepository(db_session)
    doc = await repo.upsert(
        source=DocumentSource.notion.value,
        source_id="sop-verify",
        title="Clinic hours SOP",
        content="Monday-Friday 8am-8pm.",
        url="https://www.notion.so/firstmed/hours",
    )
    assert doc.embedding is None  # not embedded at upsert time — a separate pass

    embedded = await EmbeddingService(db_session, embedder=FakeEmbedder()).backfill()
    assert embedded == 1

    refreshed = await repo.get(doc.id)
    assert refreshed is not None
    assert refreshed.embedding_model == "fake-notion-verify"
    assert isinstance(refreshed.embedding, list)
    assert all(isinstance(v, float) for v in refreshed.embedding)


def test_templates_have_no_embedding_column():
    """Pins down finding #2: templates are not part of the vector pipeline."""
    assert "embedding" not in Template.__table__.columns
    assert "embedding_model" not in Template.__table__.columns
