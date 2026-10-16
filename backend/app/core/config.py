from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables with strong typing."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application
    app_name: str = Field(default="ContractGuard", description="Application name")
    app_env: str = Field(
        default="development", description="Environment (development, staging, production)"
    )
    app_debug: bool = Field(default=True, description="Debug mode")
    app_host: str = Field(default="0.0.0.0", description="FastAPI host")
    app_port: int = Field(default=8000, description="FastAPI port")
    app_log_level: str = Field(default="INFO", description="Logging level")
    version: str = Field(default="0.1.0", description="API version")

    # Security & CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
        description="Allowed CORS origins",
    )
    secret_key: str = Field(
        default="development-secret-key-change-in-production-1234567890",
        description="Secret key for signing sessions/tokens",
    )

    # PostgreSQL Database
    postgres_server: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="contractguard", description="Database name")
    postgres_user: str = Field(default="postgres", description="Database user")
    postgres_password: str = Field(
        default="postgres_secure_password", description="Database password"
    )
    database_url: str | None = Field(
        default=None,
        description="Full database URL (defaults to postgresql+asyncpg if not set)",
    )

    # Vector Database (Qdrant)
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant HTTP port")
    qdrant_grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant API Key if enabled")
    qdrant_collection_name: str = Field(
        default="contract_clauses",
        description="Qdrant vector collection for contract clauses",
    )
    qdrant_policy_collection: str = Field(
        default="company_policies",
        description="Qdrant vector collection for company policies",
    )

    # AI / LLM Provider & Embeddings
    gemini_api_key: str | None = Field(default=None, description="Google Gemini API Key")
    gemini_default_model: str = Field(
        default="gemini-1.5-pro",
        description="Default Gemini model for agent analysis",
    )
    embedding_provider: str = Field(
        default="gemini",
        description="Embedding provider ('gemini' or 'mock' / 'deterministic')",
    )
    embedding_model: str = Field(
        default="text-embedding-004",
        description="Model name used for vector embeddings",
    )
    embedding_dimension: int = Field(
        default=768,
        description="Vector embedding dimensions (768 for text-embedding-004)",
    )

    # Policy Chunking and Retrieval Limits
    policy_chunk_size: int = Field(
        default=500,
        description="Target characters per policy chunk",
    )
    policy_chunk_overlap: int = Field(
        default=100,
        description="Character overlap between consecutive policy chunks",
    )
    policy_retrieval_limit: int = Field(
        default=5,
        description="Default maximum policy passages returned per query",
    )

    # Document Storage & Ingestion Limits
    upload_dir: str = Field(
        default="data/uploads",
        description="Secure storage directory for uploaded raw contract files",
    )
    storage_backend: str = Field(
        default="local",
        description="Storage provider ('local' or 's3')",
    )
    max_upload_size_mb: int = Field(default=25, description="Max upload file size in megabytes")
    allowed_extensions: list[str] = Field(
        default=["pdf", "docx"],
        description="Allowed contract file extensions",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def async_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached factory function for typed settings."""
    return Settings()
