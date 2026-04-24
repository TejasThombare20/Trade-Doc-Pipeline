"""Environment-driven configuration with startup validation.

Loaded exactly once at process start. Missing required vars fail fast with a
clear message so we never silently fall back to insecure defaults.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENV: Literal["dev", "prod", "test"] = "dev"
    RUN_ENV: Literal["local", "cloud"] = "local"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Database
    DATABASE_URL: PostgresDsn
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 10

    # ---- LLM Provider Selection ----
    LLM_PROVIDER: Literal["openai", "azure", "gemini"] = "openai"

    # OpenAI (required when LLM_PROVIDER=openai)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_VISION: str = "gpt-4o"
    OPENAI_MODEL_REASONING: str = "gpt-4o"
    OPENAI_MODEL_CHEAP: str = "gpt-4o-mini"

    # Azure OpenAI (required when LLM_PROVIDER=azure)
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-06-01"

    # Google Gemini (required when LLM_PROVIDER=gemini)
    GEMINI_API_KEY: str = ""

    # ---- Storage Backend Selection ----
    STORAGE_BACKEND: Literal["local", "s3", "azure_blob"] = "local"
    LOCAL_STORAGE_ROOT: str = "public"

    # AWS S3 (required when STORAGE_BACKEND=s3)
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_ENDPOINT_URL: str | None = None

    # Azure Blob Storage (required when STORAGE_BACKEND=azure_blob)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = ""

    # Pipeline safety
    COST_CAP_USD_PER_RUN: float = 0.50
    MAX_RETRIES_PER_NODE: int = 2
    LOW_CONFIDENCE_THRESHOLD: float = 0.70

    # Upload limits
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Auth (dummy tenant-level tokens for Part 1). Must be set in prod.
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    SESSION_COOKIE_NAME: str = "nova_session"
    SESSION_TTL_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    @field_validator("S3_BUCKET", "S3_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    @classmethod
    def _s3_requires_creds(cls, v: str | None, info) -> str | None:
        # Cross-field validation happens in model_post_init below.
        return v

    def model_post_init(self, __context) -> None:
        if self.STORAGE_BACKEND == "s3":
            missing = [
                k for k in ("S3_BUCKET", "S3_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
                if getattr(self, k) is None
            ]
            if missing:
                raise ValueError(
                    f"STORAGE_BACKEND=s3 requires: {', '.join(missing)}"
                )

        if self.STORAGE_BACKEND == "azure_blob":
            missing = [
                k for k in ("AZURE_STORAGE_CONNECTION_STRING", "AZURE_STORAGE_CONTAINER")
                if not getattr(self, k)
            ]
            if missing:
                raise ValueError(
                    f"STORAGE_BACKEND=azure_blob requires: {', '.join(missing)}"
                )

        # Validate that the selected LLM provider has its credentials set.
        provider = self.LLM_PROVIDER
        if provider == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        elif provider == "azure":
            missing = [
                k for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")
                if not getattr(self, k)
            ]
            if missing:
                raise ValueError(
                    f"LLM_PROVIDER=azure requires: {', '.join(missing)}"
                )
        elif provider == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
