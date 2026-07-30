"""Unit tests for settings behaviour.

These construct ``Settings`` with ``_env_file=None`` so they exercise the pure
default/assembly logic and are not perturbed by a developer's local ``.env``
(which, e.g., points ``DATABASE_URL`` at the SQLite demo DB).
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_cors_origins_parsed_from_comma_string():
    s = Settings(_env_file=None, backend_cors_origins="http://a.com, http://b.com ,http://c.com")
    assert s.backend_cors_origins == ["http://a.com", "http://b.com", "http://c.com"]


def test_database_uri_assembled_from_parts():
    s = Settings(
        _env_file=None,
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert s.sqlalchemy_database_uri == "postgresql+asyncpg://u:p@h:1234/d"


def test_database_url_override_wins():
    s = Settings(_env_file=None, database_url="postgresql+asyncpg://x/y")
    assert s.sqlalchemy_database_uri == "postgresql+asyncpg://x/y"


def test_redis_uri_assembled():
    s = Settings(_env_file=None, redis_host="r", redis_port=6380, redis_db=3)
    assert s.redis_uri == "redis://r:6380/3"


_VALID_TOKEN_KEY = "dGVzdC1mZXJuZXQta2V5LXBsYWNlaG9sZGVyLTMyYg=="
_VALID_PHI_KEY = "cGhpLWZlcm5ldC1rZXktcGxhY2Vob2xkZXItMzJieXQ="


def test_is_production_flag():
    assert (
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-strong-unique-production-secret",
            token_encryption_key=_VALID_TOKEN_KEY,
            phi_encryption_key=_VALID_PHI_KEY,
            postgres_password="a-strong-unique-db-password",
            anthropic_api_key="",  # hermetic: don't let an ambient env var trip the BAA gate
        ).is_production
        is True
    )
    assert Settings(_env_file=None, environment="development").is_production is False


def test_production_rejects_insecure_secret_key():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="change-me-in-production",
            token_encryption_key=_VALID_TOKEN_KEY,
            phi_encryption_key=_VALID_PHI_KEY,
            postgres_password="a-strong-unique-db-password",
        )


def test_production_rejects_missing_token_encryption_key():
    with pytest.raises(ValidationError, match="TOKEN_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-strong-unique-production-secret",
            phi_encryption_key=_VALID_PHI_KEY,
            postgres_password="a-strong-unique-db-password",
        )


def test_production_rejects_missing_phi_encryption_key():
    with pytest.raises(ValidationError, match="PHI_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-strong-unique-production-secret",
            token_encryption_key=_VALID_TOKEN_KEY,
            postgres_password="a-strong-unique-db-password",
        )


def test_production_rejects_default_db_password():
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-strong-unique-production-secret",
            token_encryption_key=_VALID_TOKEN_KEY,
            phi_encryption_key=_VALID_PHI_KEY,
        )


def test_production_requires_anthropic_baa_when_ai_configured():
    with pytest.raises(ValidationError, match="ANTHROPIC_BAA_SIGNED"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-strong-unique-production-secret",
            token_encryption_key=_VALID_TOKEN_KEY,
            phi_encryption_key=_VALID_PHI_KEY,
            postgres_password="a-strong-unique-db-password",
            anthropic_api_key="sk-ant-real-key",
            anthropic_baa_signed=False,
        )


def test_production_allows_ai_configured_with_baa_signed():
    s = Settings(
        _env_file=None,
        environment="production",
        secret_key="a-strong-unique-production-secret",
        token_encryption_key=_VALID_TOKEN_KEY,
        phi_encryption_key=_VALID_PHI_KEY,
        postgres_password="a-strong-unique-db-password",
        anthropic_api_key="sk-ant-real-key",
        anthropic_baa_signed=True,
    )
    assert s.ai_configured is True


def test_production_without_anthropic_key_does_not_require_baa():
    # No Anthropic key configured at all → the BAA gate doesn't apply.
    s = Settings(
        _env_file=None,
        environment="production",
        secret_key="a-strong-unique-production-secret",
        token_encryption_key=_VALID_TOKEN_KEY,
        phi_encryption_key=_VALID_PHI_KEY,
        postgres_password="a-strong-unique-db-password",
        anthropic_api_key="",  # hermetic: don't let an ambient env var trip the BAA gate
    )
    assert s.ai_configured is False
