from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="social-media-ai", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(
        default="sqlite:///./storage/social_media_ai.db",
        alias="DATABASE_URL",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    reddit_client_id: str | None = Field(default=None, alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = Field(default=None, alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="social-media-ai/0.1", alias="REDDIT_USER_AGENT")
    news_api_key: str | None = Field(default=None, alias="NEWS_API_KEY")
    news_api_base_url: str = Field(default="https://newsapi.org/v2", alias="NEWS_API_BASE_URL")
    google_trends_region: str = Field(default="US", alias="GOOGLE_TRENDS_REGION")
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    ollama_model: str = Field(default="qwen3:8b", alias="OLLAMA_MODEL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    youtube_client_secrets_file: str = Field(
        default="storage/uploads/client_secret.json",
        alias="YOUTUBE_CLIENT_SECRETS_FILE",
    )
    youtube_token_file: str = Field(
        default="storage/uploads/youtube_token.json",
        alias="YOUTUBE_TOKEN_FILE",
    )
    youtube_oauth_connection_file: str = Field(
        default="storage/uploads/youtube_connection.json",
        alias="YOUTUBE_OAUTH_CONNECTION_FILE",
    )
    session_secret_key: str = Field(default="change-me-local-session-secret", alias="SESSION_SECRET_KEY")
    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: str | None = Field(default=None, alias="GOOGLE_OAUTH_REDIRECT_URI")
    youtube_oauth_redirect_uri: str | None = Field(default=None, alias="YOUTUBE_OAUTH_REDIRECT_URI")
    google_oauth_scopes: str = Field(default="openid email profile", alias="GOOGLE_OAUTH_SCOPES")
    pipeline_worker_id: str = Field(default="local-worker", alias="PIPELINE_WORKER_ID")
    pipeline_stale_timeout_seconds: int = Field(default=3600, alias="PIPELINE_STALE_TIMEOUT_SECONDS")
    pipeline_max_retries: int = Field(default=3, alias="PIPELINE_MAX_RETRIES")
    pipeline_retry_initial_delay_seconds: int = Field(default=60, alias="PIPELINE_RETRY_INITIAL_DELAY_SECONDS")
    pipeline_retry_backoff_multiplier: int = Field(default=3, alias="PIPELINE_RETRY_BACKOFF_MULTIPLIER")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def storage_dir(self) -> Path:
        return Path("storage")


@lru_cache
def get_settings() -> Settings:
    return Settings()
