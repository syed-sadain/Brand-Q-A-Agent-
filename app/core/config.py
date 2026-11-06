"""Application configuration.

All runtime configuration is sourced from environment variables (optionally via a
local ``.env`` file). No credentials or model names are ever hard-coded.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openai", "anthropic", "google"]
EmbeddingProvider = Literal["openai", "google", "hashing"]
VectorStoreProvider = Literal["pinecone", "chroma", "memory"]
AppEnvironment = Literal["local", "development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Strongly typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ app
    app_name: str = Field(default="Brand Q&A Agent", description="Human readable app name.")
    app_env: AppEnvironment = Field(default="local", description="Deployment environment.")
    app_debug: bool = Field(default=False, description="Enable debug behaviour (never in prod).")
    api_version: str = Field(default="v1", description="Active API version prefix.")
    host: str = Field(default="0.0.0.0", description="Bind host for the ASGI server.")
    port: int = Field(default=8000, ge=1, le=65535, description="Bind port for the ASGI server.")

    # ------------------------------------------------------------------ llm
    llm_provider: LLMProvider = Field(default="openai", description="Chat LLM provider.")
    llm_model: str = Field(default="gpt-4o-mini", description="Chat model identifier.")
    llm_api_key: str | None = Field(
        default=None, description="Generic API key for the LLM provider."
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout: float = Field(default=30.0, gt=0, description="LLM request timeout in seconds.")
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    # ------------------------------------------------------------------ embeddings
    embedding_provider: EmbeddingProvider = Field(
        default="openai", description="Embedding provider."
    )
    embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model id."
    )
    embedding_api_key: str | None = Field(
        default=None, description="API key for the embedding provider."
    )
    embedding_dimension: int = Field(
        default=1536, gt=0, description="Vector dimension. Must match the index."
    )

    # ------------------------------------------------------------------ vector store
    vector_store_provider: VectorStoreProvider = Field(
        default="memory", description="Active vector store backend."
    )
    pinecone_api_key: str | None = Field(default=None)
    pinecone_index_name: str = Field(default="brand-qa-agent")
    pinecone_cloud: str = Field(default="aws")
    pinecone_region: str = Field(default="us-east-1")
    chroma_persist_dir: str = Field(default="./.chroma")
    document_registry_path: str = Field(
        default="./.data/document_registry.json",
        description="Local registry used to track chunk counts for stale-vector cleanup.",
    )

    # ------------------------------------------------------------------ retrieval / chunking
    chunk_size: int = Field(default=400, gt=0, description="Chunk size in tokens.")
    chunk_overlap: int = Field(default=50, ge=0, description="Chunk overlap in tokens.")
    retrieval_top_k: int = Field(
        default=5, ge=1, le=50, description="Number of chunks to retrieve."
    )

    # ------------------------------------------------------------------ http
    http_timeout: float = Field(default=15.0, gt=0, description="Outbound HTTP timeout in seconds.")
    http_max_bytes: int = Field(
        default=5_000_000, gt=0, description="Max bytes to download per URL."
    )
    http_max_redirects: int = Field(default=5, ge=0, le=10)
    http_user_agent: str = Field(default="BrandQAAgent/1.0 (+https://example.com/bot)")

    # ------------------------------------------------------------------ security
    allowed_url_schemes: tuple[str, ...] = Field(default=("http", "https"))
    allow_private_networks: bool = Field(
        default=False, description="Only enable for local testing."
    )

    # ------------------------------------------------------------------ logging
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=False, description="Emit structured JSON logs.")

    # ------------------------------------------------------------------ validators
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_lt_size(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size")
        if chunk_size is not None and value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value

    # ------------------------------------------------------------------ helpers
    def resolved_llm_api_key(self) -> str | None:
        """Return the API key for the configured LLM provider.

        ``LLM_API_KEY`` takes precedence; otherwise a provider specific variable is
        used (``OPENAI_API_KEY`` etc.) so that standard env files keep working.
        """
        if self.llm_api_key:
            return self.llm_api_key
        import os

        mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        return os.getenv(mapping[self.llm_provider])

    def resolved_embedding_api_key(self) -> str | None:
        """Return the API key for the configured embedding provider."""
        if self.embedding_api_key:
            return self.embedding_api_key
        import os

        if self.embedding_provider == "openai":
            return self.llm_api_key or os.getenv("OPENAI_API_KEY")
        if self.embedding_provider == "google":
            return self.llm_api_key or os.getenv("GOOGLE_API_KEY")
        return None

    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
