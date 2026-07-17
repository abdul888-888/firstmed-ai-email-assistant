"""Lexical retrieval over the unified document index (Phase 4).

Fetches candidate documents matching the query terms, then ranks them in memory
by weighted term frequency (title matches count more than body matches). This is
deliberately dependency-light; semantic (embedding) retrieval arrives in Phase 5
and can plug in behind the same :class:`SearchService` interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document import DocumentRepository

_TERM_RE = re.compile(r"\w+", re.UNICODE)
_TITLE_WEIGHT = 3
_BODY_WEIGHT = 1


def tokenize(query: str) -> list[str]:
    """Lower-cased word tokens, de-duplicated, preserving order."""
    seen: dict[str, None] = {}
    for match in _TERM_RE.findall(query.lower()):
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


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = DocumentRepository(session)

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

        scored = [
            ScoredDocument(document=doc, score=score_document(doc, terms)) for doc in candidates
        ]
        scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: (s.score, s.document.updated_at), reverse=True)
        return scored[:limit]

    async def stats(self) -> dict[str, int]:
        counts = await self.repo.counts_by_source()
        counts["total"] = sum(counts.values())
        return counts
