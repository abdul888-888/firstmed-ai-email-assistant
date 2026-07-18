"""Centralized application configuration.

All settings are read from environment variables (and an optional ``.env`` file)
via ``pydantic-settings``. Import the singleton ``settings`` anywhere:

    from app.core.config import settings
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        # Look for a .env in the backend dir first, then the repo root.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "FirstMed AI Email Assistant"
    environment: Environment = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Security / auth ---
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    # Fernet key (urlsafe base64, 32 bytes) for encrypting stored OAuth tokens.
    # Empty => a deterministic key is derived from ``secret_key`` (dev only).
    token_encryption_key: str = ""

    # --- Frontend ---
    # Where the OAuth callback redirects the browser after login succeeds.
    frontend_base_url: str = "http://localhost:3000"

    # --- Google OAuth / Gmail (Phase 2) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Shared clinical inbox address; empty => operate on the signed-in mailbox ("me").
    gmail_shared_inbox: str = ""
    # Scopes requested at consent: OIDC identity + read Gmail + create/send drafts.
    google_oauth_scopes: list[str] = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    # --- Notion (Phase 3) ---
    notion_api_key: str = ""
    notion_root_page_id: str = ""
    notion_version: str = "2022-06-28"

    # --- AI (Phase 5) ---
    anthropic_api_key: str = ""
    # Active, cost-friendly default. Haiku 4.5 supports structured outputs (triage)
    # but NOT adaptive thinking — the AI client gates thinking on model support.
    ai_model: str = "claude-haiku-4-5"
    ai_max_tokens: int = 4096

    # --- Embeddings / semantic retrieval (Phase 9) ---
    # Provider is swappable: local (fastembed, no key) | openai | voyage.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    openai_api_key: str = ""
    voyage_api_key: str = ""
    # How the index ranks: hybrid (lexical + semantic RRF) | semantic | lexical.
    retrieval_mode: str = "hybrid"

    # --- Database ---
    postgres_user: str = "firstmed"
    postgres_password: str = "firstmed"
    postgres_db: str = "firstmed"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str | None = None

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str | None = None

    # --- Celery ---
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    @field_validator("backend_cors_origins", "google_oauth_scopes", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow a comma- (or space-) separated string from the environment."""
        if isinstance(value, str):
            parts = value.replace(",", " ").split()
            return [item for item in (p.strip() for p in parts) if item]
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def google_oauth_configured(self) -> bool:
        """True when client id/secret are set (so the SSO flow can run)."""
        return bool(self.google_client_id and self.google_client_secret)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def notion_configured(self) -> bool:
        """True when a Notion integration token is set."""
        return bool(self.notion_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_configured(self) -> bool:
        """True when an Anthropic API key is set."""
        return bool(self.anthropic_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embedding_configured(self) -> bool:
        """True when the selected embedding provider can be used.

        ``local`` needs no key (the fastembed dependency is checked at runtime and
        degrades to lexical search if absent); the API providers need their key.
        """
        provider = self.embedding_provider.lower()
        if provider == "local":
            return True
        if provider == "openai":
            return bool(self.openai_api_key)
        if provider == "voyage":
            return bool(self.voyage_api_key)
        return False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_uri(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
