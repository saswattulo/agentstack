from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "prod", "test"] = "dev"
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    dev_api_key: str = "dev-local-key-change-me"
    dev_user_email: str = "dev@example.com"

    jwt_secret_key: str = "change-me-in-prod-please-this-is-not-safe"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60 * 24
    jwt_issuer: str = "agentstack"

    postgres_user: str = "agentstack"
    postgres_password: str = "agentstack"
    postgres_db: str = "agentstack"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str | None = None

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str | None = None

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: str | None = None

    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    groq_api_key: str | None = None
    groq_chat_model: str = "qwen/qwen3-32b"
    groq_fallback_model: str = "llama-3.3-70b-versatile"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"

    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = False

    tavily_api_key: str | None = None

    phoenix_collector_endpoint: str = "http://phoenix:6006"
    phoenix_project_name: str = "agentstack"

    rate_limit_per_minute: int = 60
    rate_limit_per_day: int = 10_000

    chunk_size: int = 512
    chunk_overlap: int = 64
    ingest_max_file_mb: int = 50

    llm_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.95
    cache_ttl_seconds: int = 86_400

    # Voice (Week 4)
    voice_enabled: bool = True
    voice_asr_model: str = "whisper-large-v3"
    voice_tts_model_path: str = "/models/piper/en_US-amy-medium.onnx"
    voice_vad_silence_ms: int = 800
    voice_vad_min_utterance_ms: int = 250
    voice_vad_max_utterance_ms: int = 30_000
    voice_max_concurrent_sessions_per_user: int = 3

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_sqlalchemy_url(self) -> str:
        return self.sqlalchemy_url.replace("+asyncpg", "+psycopg")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_dsn(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or f"redis://{self.redis_host}:{self.redis_port}/1"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or f"redis://{self.redis_host}:{self.redis_port}/2"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
