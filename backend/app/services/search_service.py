"""Retrieval over the unified document index (Phase 4 lexical + Phase 9 semantic).

Ranks documents by weighted term frequency (lexical) and/or embedding cosine
similarity (semantic), fusing the two with Reciprocal Rank Fusion in the default
``hybrid`` mode. Semantic ranking is best-effort: when no embedder is available or
no documents are embedded yet, it degrades cleanly to the original lexical
behavior. Callers (`DraftService`, `TriageService`, `/search`) are unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import cosine_similarity
from app.core.config import settings
from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.services.embedding_service import EmbeddingService

_TERM_RE = re.compile(r"\w+", re.UNICODE)
_TITLE_WEIGHT = 3
_BODY_WEIGHT = 1

# Common words carry no retrieval signal; without this, function words ("the",
# "before", "my") make almost every document match, drowning the real hits.
_STOPWORDS = frozenset(
    """
    a an and are as at be been before but by can could did do does for from get got had has have
    how i if in into is it its me my need of on or our so than that the their them then there these
    they this to us was we were what when where which who will with would you your
    """.split()
)
# Reciprocal Rank Fusion constant (standard default).
_RRF_K = 60
# How many documents to consider for semantic scoring.
_SEMANTIC_POOL = 500


def tokenize(query: str) -> list[str]:
    """Lower-cased word tokens: de-duplicated, stopwords removed, order preserved."""
    seen: dict[str, None] = {}
    for match in _TERM_RE.findall(query.lower()):
        if match not in _STOPWORDS:
            seen.setdefault(match, None)
    return list(seen)


@dataclass(slots=True)
class ScoredDocument:
    document: Document
    score: float


def score_document(doc: Document, terms: list[str]) -> float:
    if not terms:
        return 0.0
    title = doc.title.lower()
    content = doc.content.lower()
    score = 0
    for term in terms:
        score += title.count(term) * _TITLE_WEIGHT
        score += content.count(term) * _BODY_WEIGHT
    return float(score)


def _reciprocal_rank_fusion(
    lexical: list[ScoredDocument], semantic: list[ScoredDocument], limit: int
) -> list[ScoredDocument]:
    """Fuse two rankings by RRF: score = Σ 1/(k + rank) across the lists."""
    fused: dict[object, dict] = {}
    for ranking in (lexical, semantic):
        for rank, s in enumerate(ranking, start=1):
            entry = fused.setdefault(s.document.id, {"doc": s.document, "score": 0.0})
            entry["score"] += 1.0 / (_RRF_K + rank)
    results = [ScoredDocument(document=e["doc"], score=e["score"]) for e in fused.values()]
    results.sort(key=lambda s: s.score, reverse=True)
    return results[:limit]


class SearchService:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingService | None = None) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.embeddings = embeddings or EmbeddingService(session)

    async def search(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> list[ScoredDocument]:
        terms = tokenize(query)
        candidates = await self.repo.fetch_candidates(terms, sources=sources)

        if not terms:
            # Browse mode: candidates already ordered by recency.
            return [ScoredDocument(document=doc, score=0.0) for doc in candidates[:limit]]

        lexical = [
            ScoredDocument(document=doc, score=score_document(doc, terms)) for doc in candidates
        ]
        lexical = [s for s in lexical if s.score > 0]
        lexical.sort(key=lambda s: (s.score, s.document.updated_at), reverse=True)

        mode = settings.retrieval_mode.lower()
        if mode == "lexical":
            return lexical[:limit]

        semantic = await self._semantic(query, sources)
        if not semantic:
            # No embedded docs / no embedder → preserve lexical behavior.
            return lexical[:limit]
        if mode == "semantic":
            return semantic[:limit]
        return _reciprocal_rank_fusion(lexical, semantic, limit)

    async def _semantic(
        self, query: str, sources: list[str] | None
    ) -> list[ScoredDocument]:
        """Cosine-ranked documents for the query, or [] if unavailable."""
        pool = await self.repo.fetch_candidates([], sources=sources, limit=_SEMANTIC_POOL)
        embeddable = [d for d in pool if d.embedding]
        if not embeddable:
            return []
        qvec = await self.embeddings.embed_query(query)
        if qvec is None:
            return []
        scored = [
            ScoredDocument(document=d, score=cosine_similarity(qvec, d.embedding))
            for d in embeddable
        ]
        scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored

    async def stats(self) -> dict[str, int]:
        counts = await self.repo.counts_by_source()
        counts["total"] = sum(counts.values())
        return counts
