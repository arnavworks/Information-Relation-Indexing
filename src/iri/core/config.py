"""Validated runtime configuration, sourced only from IRI_* variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by API workers.

    Secrets intentionally have no production defaults. The local defaults match
    ``compose.yaml`` and are suitable only for a developer workstation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IRI_",
        extra="ignore",
    )

    service_name: str = "information-relation-index"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/v1"

    postgres_dsn: str = "postgresql+psycopg://continuum:continuum@localhost:5432/continuum"
    neo4j_dsn: str = "bolt://neo4j:continuum-local@localhost:7687"
    neo4j_database: str = "neo4j"

    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("IRI_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    embedding_model: str = "gemini-embedding-001"
    extraction_model: str = "gemini-2.0-flash"
    answer_model: str = "gemini-2.0-flash"
    answer_max_sources: int = Field(default=24, ge=1, le=100)
    upload_directory: Path = Path("data/uploads")
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    retrieval_default_limit: int = Field(default=8, ge=1, le=100)
    cors_origins: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-by-convention settings object per process."""

    return Settings()
