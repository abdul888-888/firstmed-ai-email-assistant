"""Embedding providers for semantic retrieval (Phase 9).

A tiny provider-agnostic interface so the vector representation is swappable via
``EMBEDDING_PROVIDER`` (``local`` | ``openai`` | ``voyage``) with no change to the
retrieval code. The default is **local** (``fastembed``) — no API key, offline,
no per-call cost. Heavy/optional deps are imported lazily so the app boots (and
degrades to lexical search) even when a provider's library or key is missing.
"""

from __future__ import annotations

import asyncio
import math
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingError(Exception):
    """Raised when embeddings cannot be produced (missing dep/key/provider)."""


class Embedder(Protocol):
    model: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is empty)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class LocalEmbedder:
    """`fastembed` (ONNX) — runs locally, no key. Downloads the model on first use."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._model = None  # lazy — loading pulls the ONNX weights

    def _ensure(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise EmbeddingError(
                    "fastembed is not installed — run `pip install fastembed` "
                    "or set EMBEDDING_PROVIDER=openai|voyage"
                ) from exc
            self._model = TextEmbedding(model_name=self.model)
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure()
        return [list(map(float, vec)) for vec in model.embed(texts)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        vecs = await asyncio.to_thread(self._embed_sync, [text])
        return vecs[0]


class OpenAIEmbedder:
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise EmbeddingError("openai is not installed") from exc
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        client = self._ensure()
        try:
            resp = await client.embeddings.create(model=self.model, input=texts)
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise EmbeddingError(f"OpenAI embeddings failed: {exc}") from exc
        return [d.embedding for d in resp.data]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


class VoyageEmbedder:
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                import voyageai
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise EmbeddingError("voyageai is not installed") from exc
            self._client = voyageai.AsyncClient(api_key=self._api_key)
        return self._client

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        client = self._ensure()
        try:
            result = await client.embed(texts, model=self.model, input_type=input_type)
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise EmbeddingError(f"Voyage embeddings failed: {exc}") from exc
        return result.embeddings

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "document")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]


def build_embedder() -> Embedder:
    """Construct the configured embedder (does not load the model yet)."""
    provider = settings.embedding_provider.lower()
    if provider == "local":
        return LocalEmbedder(settings.embedding_model)
    if provider == "openai":
        if not settings.openai_api_key:
            raise EmbeddingError("OPENAI_API_KEY is not set")
        return OpenAIEmbedder(settings.embedding_model, settings.openai_api_key.get_secret_value())
    if provider == "voyage":
        if not settings.voyage_api_key:
            raise EmbeddingError("VOYAGE_API_KEY is not set")
        return VoyageEmbedder(settings.embedding_model, settings.voyage_api_key.get_secret_value())
    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")


# Cached singleton (loads the local model once). ``False`` marks a prior failure
# so we don't retry a missing dependency on every search.
_cached: Embedder | bool | None = None


def get_embedder() -> Embedder | None:
    """Return the configured embedder, or ``None`` if unavailable/unconfigured.

    Never raises — semantic retrieval is best-effort and falls back to lexical.
    """
    global _cached
    if _cached is False:
        return None
    if _cached is not None:
        return _cached  # type: ignore[return-value]
    if not settings.embedding_configured:
        _cached = False
        return None
    try:
        _cached = build_embedder()
        return _cached
    except EmbeddingError as exc:
        logger.warning("embeddings.unavailable", error=str(exc))
        _cached = False
        return None


def reset_embedder_cache() -> None:
    """Clear the cached embedder (tests / config changes)."""
    global _cached
    _cached = None
