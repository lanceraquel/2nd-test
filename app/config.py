from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./atlas_pipeline.db", alias="DATABASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    openai_review_model: str = Field(default="gpt-5", alias="OPENAI_REVIEW_MODEL")
    openai_reasoning_effort: str = Field(default="medium", alias="OPENAI_REASONING_EFFORT")
    max_qc_retries: int = Field(default=5, alias="MAX_QC_RETRIES")
    worker_poll_interval_seconds: int = Field(default=15, alias="WORKER_POLL_INTERVAL_SECONDS")
    default_max_findings: int = Field(default=8, alias="DEFAULT_MAX_FINDINGS")
    report_output_dir: str = Field(default="reports", alias="REPORT_OUTPUT_DIR")
    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
