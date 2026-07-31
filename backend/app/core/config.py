"""Centralized application configuration.

All settings are read from environment variables (and an optional ``.env`` file)
via ``pydantic-settings``. Import the singleton ``settings`` anywhere:

    from app.core.config import settings
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]

# Dev-only placeholder values that must never reach a production deployment.
_INSECURE_SECRET_KEYS = frozenset({"", "change-me-in-production", "changeme", "secret"})
_INSECURE_DB_PASSWORDS = frozenset({"", "firstmed", "changeme", "password", "postgres"})


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
    secret_key: SecretStr = SecretStr("change-me-in-production")
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"
    backend_cors_origins: list[str] | str = ["http://localhost:3000"]
    # Fernet key (urlsafe base64, 32 bytes) for encrypting stored OAuth tokens.
    # Empty => a deterministic key is derived from ``secret_key`` (dev only).
    token_encryption_key: SecretStr = SecretStr("")
    # Separate Fernet key protecting patient-identifying review content at rest
    # (see app.models.types.EncryptedText) — independent from the token key so
    # the two can be rotated separately. Empty => dev-only derived fallback.
    phi_encryption_key: SecretStr = SecretStr("")

    # --- Frontend ---
    # Where the OAuth callback redirects the browser after login succeeds.
    frontend_base_url: str = "http://localhost:3000"

    # --- Google OAuth / Gmail (Phase 2) ---
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Shared clinical inbox address; empty => operate on the signed-in mailbox ("me").
    gmail_shared_inbox: str = ""
    # Scopes requested at consent: OIDC identity + read Gmail + create/send drafts.
    google_oauth_scopes: list[str] | str = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    # --- Notion (Phase 3) ---
    notion_api_key: SecretStr = SecretStr("")
    notion_root_page_id: str = ""
    notion_version: str = "2022-06-28"

    # --- Healzz (Phase 10) ---
    healzz_api_base_url: str = ""
    healzz_api_key: SecretStr = SecretStr("")

    # --- AI (Phase 5) ---
    anthropic_api_key: SecretStr = SecretStr("")
    # Active, cost-friendly default. Haiku 4.5 supports structured outputs (triage)
    # but NOT adaptive thinking — the AI client gates thinking on model support.
    ai_model: str = "claude-haiku-4-5"
    ai_max_tokens: int = 4096
    # Self-attestation only — set true once your organization has confirmed a
    # signed BAA (HIPAA) and/or DPA (GDPR) with Anthropic covering this API
    # usage. Not verified against anything external; see
    # docs/security/phi-encryption-and-anthropic-baa.md for what to request.
    # In production, sending real patient data via a configured API key
    # without this confirmed is refused at startup (see the validator below).
    anthropic_baa_signed: bool = False

    # --- Embeddings / semantic retrieval (Phase 9) ---
    # Provider is swappable: local (fastembed, no key) | openai | voyage.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    openai_api_key: SecretStr = SecretStr("")
    voyage_api_key: SecretStr = SecretStr("")
    # How the index ranks: hybrid (lexical + semantic RRF) | semantic | lexical.
    retrieval_mode: str = "hybrid"

    # --- Database ---
    postgres_user: str = "firstmed"
    postgres_password: SecretStr = SecretStr("firstmed")
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
    # How often the Beat-scheduled task fans out an automatic pull to every
    # connected mailbox (see app.tasks.workflow_tasks.pull_all_connected_task).
    # Only takes effect while a `celery beat` process is running.
    gmail_auto_pull_interval_seconds: int = 300

    @field_validator("backend_cors_origins", "google_oauth_scopes", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> list[str]:
        """Allow a comma-, space-separated, plain URL, or JSON string from the environment."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("[") and value.endswith("]"):
                import json
                try:
                    res = json.loads(value)
                    if isinstance(res, list):
                        return [str(x) for x in res]
                except Exception:
                    pass
            parts = value.replace(",", " ").split()
            return [item for item in (p.strip() for p in parts) if item]
        if isinstance(value, list):
            return [str(x) for x in value]
        return []

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
    def healzz_configured(self) -> bool:
        """True when both the Healzz base URL and API key are set."""
        return bool(self.healzz_api_base_url and self.healzz_api_key)

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
            url = str(self.database_url)
            # Ensure Railway's URL uses asyncpg instead of default psycopg2
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+asyncpg://", 1)
            if url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
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

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        """Fail fast on insecure/placeholder secrets when running in production."""
        if self.environment != "production":
            return self

        problems: list[str] = []
        if self.secret_key.get_secret_value().strip().lower() in _INSECURE_SECRET_KEYS:
            problems.append("SECRET_KEY must be set to a strong, unique value")
        if not self.token_encryption_key.get_secret_value():
            problems.append(
                "TOKEN_ENCRYPTION_KEY must be set explicitly (no derived dev fallback)"
            )
        if not self.phi_encryption_key.get_secret_value():
            problems.append(
                "PHI_ENCRYPTION_KEY must be set explicitly (no derived dev fallback) — "
                "protects patient data at rest"
            )
        if not self.database_url and self.postgres_password.get_secret_value().strip().lower() in _INSECURE_DB_PASSWORDS:
            problems.append("POSTGRES_PASSWORD must not use a development default")
        if self.ai_configured and not self.anthropic_baa_signed:
            problems.append(
                "ANTHROPIC_BAA_SIGNED must be true before processing real patient data "
                "through the Anthropic API in production — confirm a signed BAA/DPA with "
                "Anthropic first (see docs/security/phi-encryption-and-anthropic-baa.md)"
            )

        if problems:
            raise ValueError(
                "Insecure configuration for environment=production: " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()


settings = get_settings()
