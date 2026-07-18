"""Embedding indexer for the document store (Phase 9).

Backfills document vectors and embeds search queries. Best-effort: if no embedder
is available (dependency/key missing), backfill is a no-op and search falls back
to lexical ranking.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import Embedder, get_embedder
from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.document import DocumentRepository

logger = get_logger(__name__)

# Embed title + content together so the vector reflects both.
_EMBED_CHARS = 4000


class EmbeddingService:
    def __init__(self, session: AsyncSession, embedder: Embedder | None = None) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        # Explicit None means "use the configured default"; callers/tests may inject.
        self._embedder = embedder if embedder is not None else get_embedder()

    @property
    def available(self) -> bool:
        return self._embedder is not None

    @property
    def model_name(self) -> str:
        return getattr(self._embedder, "model", settings.embedding_model)

    async def embed_query(self, text: str) -> list[float] | None:
        if self._embedder is None or not text.strip():
            return None
        try:
            return await self._embedder.embed_query(text)
        except Exception as exc:  # noqa: BLE001 - best-effort; fall back to lexical
            logger.warning("embeddings.query_failed", error=str(exc))
            return None

    async def backfill(self, *, limit: int = 1000) -> int:
        """Embed documents missing an up-to-date vector. Returns the count embedded."""
        if self._embedder is None:
            logger.info("embeddings.backfill_skipped", reason="no embedder")
            return 0
        docs = await self.repo.list_needing_embedding(self.model_name, limit=limit)
        if not docs:
            return 0
        texts = [f"{d.title}\n{d.content}"[:_EMBED_CHARS] for d in docs]
        try:
            vectors = await self._embedder.embed_documents(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings.backfill_failed", error=str(exc))
            return 0
        for doc, vec in zip(docs, vectors, strict=False):
            await self.repo.set_embedding(doc, embedding=vec, model=self.model_name)
        logger.info("embeddings.backfilled", count=len(docs), model=self.model_name)
        return len(docs)
