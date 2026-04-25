# kb/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KB_",
        extra="ignore",
    )

    app_name: str = "GPGPU Knowledge Base"
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Storage
    data_dir: str = "./data"
    database_url: str = "sqlite:///./data/kb.sqlite"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_dir: str = "./data/chroma"

    # LLM provider abstraction
    # Options: "hermes" (default — uses local hermes CLI), "anthropic", "openai"
    llm_provider: str = "hermes"
    llm_timeout_seconds: int = 180
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Ingestion
    github_token: str | None = None
    arxiv_per_category: int = 50

    # API limits
    chat_query_max_len: int = 2000
    chat_top_k_max: int = 20

    # Optional bearer token guarding /api/chat. When None, the endpoint is
    # open (preserves frictionless local dev). When set, callers must send
    # `Authorization: Bearer <token>` or get 401.
    chat_token: str | None = None


settings = Settings(
    # Allow standard provider envs without KB_ prefix as a convenience
    anthropic_api_key=os.getenv("KB_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
    openai_api_key=os.getenv("KB_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
    github_token=os.getenv("KB_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN"),
)
