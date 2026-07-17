"""Unit tests for settings behaviour."""

from __future__ import annotations

from app.core.config import Settings


def test_cors_origins_parsed_from_comma_string():
    s = Settings(backend_cors_origins="http://a.com, http://b.com ,http://c.com")
    assert s.backend_cors_origins == ["http://a.com", "http://b.com", "http://c.com"]


def test_database_uri_assembled_from_parts():
    s = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )
    assert s.sqlalchemy_database_uri == "postgresql+asyncpg://u:p@h:1234/d"


def test_database_url_override_wins():
    s = Settings(database_url="postgresql+asyncpg://x/y")
    assert s.sqlalchemy_database_uri == "postgresql+asyncpg://x/y"


def test_redis_uri_assembled():
    s = Settings(redis_host="r", redis_port=6380, redis_db=3)
    assert s.redis_uri == "redis://r:6380/3"


def test_is_production_flag():
    assert Settings(environment="production").is_production is True
    assert Settings(environment="development").is_production is False
