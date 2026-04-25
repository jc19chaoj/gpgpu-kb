# kb/config.py
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load backend/.env into os.environ before constructing Settings so the
# un-prefixed convenience names below (ANTHROPIC_API_KEY, OPENAI_API_KEY,
# DEEPSEEK_API_KEY, GITHUB_TOKEN) resolve. pydantic-settings on its own
# only reads KB_-prefixed keys from .env because of env_prefix="KB_".
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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
    # Options: "hermes" (default — uses local hermes CLI), "anthropic", "openai", "deepseek"
    llm_provider: str = "hermes"
    llm_timeout_seconds: int = 180
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

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
    deepseek_api_key=os.getenv("KB_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
    github_token=os.getenv("KB_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN"),
)
