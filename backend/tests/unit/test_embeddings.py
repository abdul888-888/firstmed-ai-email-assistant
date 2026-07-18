"""Unit tests for the embedding abstraction + gating."""

from __future__ import annotations

from app.ai.embeddings import cosine_similarity, get_embedder, reset_embedder_cache
from app.core.config import settings
from pydantic import SecretStr


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert round(cosine_similarity([1.0, 1.0], [2.0, 2.0]), 6) == 1.0


def test_get_embedder_none_when_provider_unconfigured(monkeypatch):
    # OpenAI provider without a key → not configured → no embedder (lexical fallback).
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    reset_embedder_cache()
    assert get_embedder() is None
    reset_embedder_cache()


def test_get_embedder_none_for_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "nope")
    reset_embedder_cache()
    assert get_embedder() is None
    reset_embedder_cache()
