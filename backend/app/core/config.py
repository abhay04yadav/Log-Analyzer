"""Application settings, read from environment variables or backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Smart Log Analyzer"
    environment: str = "development"

    # storage / messaging -- PostgreSQL + Redis Streams in Docker, SQLite + in-memory queue in lite mode
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'sla.db').as_posix()}"
    redis_url: str | None = None

    # security
    secret_key: str = "dev-only-secret-change-me-0123456789abcdef"
    admin_username: str = "admin"
    admin_password: str = "admin123"
    token_ttl_minutes: int = 720
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # default project used by the demo + simulator
    demo_project_name: str = "ShopFlow (demo)"
    demo_api_key: str = "sla_demo_ingest_key"

    # AI provider (S7). Without a key the system still works: playbooks + rule-based recommendations.
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"            # fast (~3-8 s), good quality on evidence packs
    gemini_fallback_model: str | None = "gemini-3.5-flash"  # used if the primary model fails
    llm_timeout_seconds: float = 45.0

    # analysis
    code_repo_path: str = str(BACKEND_DIR / "sample_repo")
    incident_gap_seconds: int = 300          # quiet time after which a new incident is opened
    deployment_lookback_minutes: int = 30
    recommend_debounce_seconds: float = 3.0  # wait for an incident to settle before asking the LLM

    # ingestion limits
    max_batch_events: int = 1000
    max_message_chars: int = 16000
    ingest_rate_per_minute: int = 1200

    run_worker: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider == "gemini" and bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
