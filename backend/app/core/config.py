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

    # LLM Provider Abstraction
    llm_provider: str = Field(
        default="gemini",
        description="LLM provider for clause extraction ('gemini' or 'mock')",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model name (defaults to GEMINI_DEFAULT_MODEL when unset)",
    )
    llm_timeout_seconds: float = Field(
        default=45.0,
        description="Per-request LLM timeout in seconds",
    )
    llm_max_retries: int = Field(
        default=2,
        description="Number of retries after the initial LLM request fails",
    )
    llm_max_output_tokens: int = Field(
        default=8192,
        description="Maximum output tokens requested from the LLM",
    )

    # Clause Extraction Chunking
    clause_chunk_size: int = Field(
        default=6000,
        description="Target characters per clause extraction chunk",
    )
    clause_chunk_overlap: int = Field(
        default=600,
        description="Character overlap between consecutive clause extraction chunks",
    )
    clause_min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence below which an extracted clause is flagged for review",
    )

    # Policy Retrieval Agent
    policy_retrieval_limit: int = Field(
        default=5,
        description="Maximum active policy evidence passages returned per clause",
    )
    policy_retrieval_min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for clause-to-policy retrieval",
    )
    policy_retrieval_statuses: list[str] = Field(
        default=["active"],
        description="Policy statuses eligible for retrieval and risk analysis",
    )

    # Risk Analysis Agent
    risk_analysis_enable_model: bool = Field(
        default=True,
        description="Enable model-assisted mismatch analysis after deterministic rules",
    )
    risk_severity_liability_unlimited: str = Field(
        default="critical",
        description="Review priority when contract liability is unlimited",
    )
    risk_severity_liability_cap: str = Field(
        default="high",
        description="Review priority for a liability cap deviation",
    )
    risk_severity_termination_notice: str = Field(
        default="high",
        description="Review priority for insufficient termination notice",
    )
    risk_severity_payment_period: str = Field(
        default="medium",
        description="Review priority for a payment period deviation",
    )
    risk_severity_policy_deviation: str = Field(
        default="medium",
        description="Default review priority for a model-identified policy deviation",
    )
    risk_severity_missing_data_protection: str = Field(
        default="high",
        description="Review priority when an active policy requires a missing data-protection clause",
    )
    risk_severity_missing_clause: str = Field(
        default="high",
        description="Default review priority for a required but missing clause category",
    )
    risk_severity_missing_evidence: str = Field(
        default="informational",
        description="Review priority when no relevant policy evidence exists",
    )
    risk_severity_possible_legal_concern: str = Field(
        default="informational",
        description="Review priority for an unverified possible legal concern",
    )
    risk_required_clause_categories: list[str] = Field(
        default_factory=list,
        description=(
            "Additional clause categories always treated as required; categories are also "
            "inferred from the active policy corpus"
        ),
    )

    # Evidence Validation / Critic Agent
    validation_enable: bool = Field(
        default=True,
        description="Automatically validate risk findings after analysis",
    )
    validation_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum bounded correction retries per finding",
    )
    validation_explanation_min_overlap: int = Field(
        default=2,
        ge=1,
        description="Minimum meaningful citation tokens an explanation must share",
    )
    validation_duplicate_detection: bool = Field(
        default=True,
        description="Reject duplicate findings that share a deterministic fingerprint",
    )

    # LangGraph Workflow Orchestration & Human Review
    workflow_review_api_key: str = Field(
        default="dev-workflow-review-key",
        description="API key required to start, inspect, or resume human review workflows",
    )
    workflow_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum automatic graph retries after validation corrections",
    )
    workflow_max_steps: int = Field(
        default=30,
        ge=5,
        le=100,
        description="Maximum graph node steps before the workflow fails safely",
    )
    workflow_max_revisions: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum human-requested revision cycles",
    )
    workflow_checkpoint_backend: str = Field(
        default="auto",
        description="Checkpoint backend: auto, postgres, sqlite, or memory",
    )
    workflow_checkpoint_database_url: str | None = Field(
        default=None,
        description="Optional PostgreSQL connection string for LangGraph checkpoints",
    )
    workflow_checkpoint_sqlite_path: str = Field(
        default="data/langgraph_checkpoints.db",
        description="SQLite checkpoint database path used for local development/tests",
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

    @property
    def resolved_llm_model(self) -> str:
        """Effective model name for the configured LLM provider."""
        return self.llm_model or self.gemini_default_model


@lru_cache
def get_settings() -> Settings:
    """Cached factory function for typed settings."""
    return Settings()
