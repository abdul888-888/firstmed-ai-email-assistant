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
    backend_cors_origins: list[str] | str = ["http://localhost:3000", "https://firstmed-ai-email-assistant.vercel.app"]
    token_encryption_key: SecretStr = SecretStr("")
    phi_encryption_key: SecretStr = SecretStr("")

    # --- Frontend ---
    frontend_base_url: str = "http://localhost:3000"

    # --- Google OAuth / Gmail (Phase 2) ---
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    gmail_shared_inbox: str = ""
    google_oauth_scopes: list[str] | str = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    # --- Microsoft Graph / Outlook (Phase 4) ---
    outlook_client_id: str = ""
    outlook_client_secret: SecretStr = SecretStr("")
    outlook_tenant_id: str = "common"
    outlook_redirect_uri: str = ""

    # --- IMAP/SMTP defaults (Phase 3) ---
    imap_default_port: int = 993
    smtp_default_port: int = 587

    # --- Notion (Phase 3) ---
    notion_api_key: SecretStr = SecretStr("")
    notion_root_page_id: str = ""
    notion_version: str = "2022-06-28"

    # --- Healzz (Phase 10) ---
    healzz_api_base_url: str = ""
    healzz_api_key: SecretStr = SecretStr("")

    # --- AI (Phase 5) ---
    # Supports Anthropic Claude and Groq Llama models
    # Set ANTHROPIC_API_KEY for Claude, GROQ_API_KEY for Groq
    # Model auto-detection: claude-* uses Anthropic, llama-*/mixtral-* uses Groq
    groq_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    ai_model: str = "claude-3-5-sonnet-20241022"  # Changed from Groq default for consistency
    ai_max_tokens: int = 4096
    anthropic_baa_signed: bool = False

    # --- Embeddings / semantic retrieval (Phase 9) ---
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    openai_api_key: SecretStr = SecretStr("")
    voyage_api_key: SecretStr = SecretStr("")
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
    gmail_auto_pull_interval_seconds: int = 300

    @field_validator("backend_cors_origins", "google_oauth_scopes", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> list[str]:
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
        return bool(self.google_client_id and self.google_client_secret)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outlook_configured(self) -> bool:
        return bool(self.outlook_client_id and self.outlook_client_secret.get_secret_value())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def imap_smtp_configured(self) -> bool:
        return True  # Ready to accept IMAP connections; no server-side config needed

    @computed_field  # type: ignore[prop-decorator]
    @property
    def notion_configured(self) -> bool:
        return bool(self.notion_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def healzz_configured(self) -> bool:
        return bool(self.healzz_api_base_url and self.healzz_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_configured(self) -> bool:
        """True when either a Groq or Anthropic API key is set."""
        return bool(
            self.groq_api_key.get_secret_value()
            or self.anthropic_api_key.get_secret_value()
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embedding_configured(self) -> bool:
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
        if self.anthropic_api_key.get_secret_value() and not self.anthropic_baa_signed:
            problems.append(
                "ANTHROPIC_BAA_SIGNED must be true before processing real patient data "
                "through the Anthropic API in production"
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