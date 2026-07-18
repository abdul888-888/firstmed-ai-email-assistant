"""Unit tests for lexical + semantic search ranking."""

from __future__ import annotations

from app.core.config import settings
from app.models.document import DocumentSource
from app.repositories.document import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.search_service import SearchService, tokenize

# Deterministic fake embedder: maps synonyms onto 3 "concept" dimensions so
# semantic similarity is testable without a real model.
_CONCEPTS = {
    "refill": 0, "prescription": 0, "medication": 0, "renew": 0, "renewal": 0,
    "dosage": 0, "pharmacy": 0,
    "billing": 1, "invoice": 1, "payment": 1, "insurance": 1,
    "appointment": 2, "schedule": 2, "scheduling": 2, "booking": 2,
}


class FakeEmbedder:
    model = "fake-concepts"

    def _vec(self, text: str) -> list[float]:
        v = [0.0, 0.0, 0.0]
        for tok in tokenize(text):
            idx = _CONCEPTS.get(tok)
            if idx is not None:
                v[idx] += 1.0
        return v

    async def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    async def embed_query(self, text):
        return self._vec(text)


async def _seed_semantic(db_session):
    repo = DocumentRepository(db_session)
    await repo.upsert(
        source=DocumentSource.notion.value, source_id="refill",
        title="Prescription refill request",
        content="prescription refill dosage pharmacy",
    )
    await repo.upsert(
        source=DocumentSource.notion.value, source_id="billing",
        title="Billing FAQ", content="invoice billing payment insurance",
    )
    await repo.upsert(
        source=DocumentSource.notion.value, source_id="appt",
        title="Scheduling SOP", content="schedule appointment booking",
    )
    emb = EmbeddingService(db_session, embedder=FakeEmbedder())
    embedded = await emb.backfill()
    return emb, embedded


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


# --- semantic / hybrid (Phase 9) ------------------------------------------


async def test_backfill_embeds_all_docs(db_session):
    emb, embedded = await _seed_semantic(db_session)
    assert embedded == 3
    docs = await DocumentRepository(db_session).fetch_candidates([], sources=None)
    assert all(d.embedding and d.embedding_model == "fake-concepts" for d in docs)


async def test_semantic_finds_paraphrase_lexical_misses(db_session, monkeypatch):
    # "renew my medication" shares NO token with the refill doc's content, so
    # lexical scores it 0 — but semantically it's the refill SOP.
    emb, _ = await _seed_semantic(db_session)
    query = "renew my medication"

    monkeypatch.setattr(settings, "retrieval_mode", "lexical")
    lexical = await SearchService(db_session, embeddings=emb).search(query)
    assert lexical == []  # lexical misses it entirely

    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    hits = await SearchService(db_session, embeddings=emb).search(query)
    assert hits[0].document.source_id == "refill"  # semantic recovers it


async def test_semantic_mode_ranks_by_meaning(db_session, monkeypatch):
    emb, _ = await _seed_semantic(db_session)
    monkeypatch.setattr(settings, "retrieval_mode", "semantic")
    hits = await SearchService(db_session, embeddings=emb).search("insurance payment question")
    assert hits[0].document.source_id == "billing"


async def test_hybrid_falls_back_to_lexical_without_embeddings(db_session, monkeypatch):
    # No backfill → no doc embeddings → hybrid must behave exactly like lexical.
    await _seed(db_session)
    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    hits = await SearchService(db_session).search("prescription")
    assert [h.document.source_id for h in hits] == ["g1", "n2"]
