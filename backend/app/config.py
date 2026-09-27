"""应用配置：全部通过环境变量 / .env 注入。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULTS = {"change-me", "change-me-before-deploy"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 应用
    env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    admin_api_key: str = "change-me-before-deploy"
    cors_origins: str = "http://localhost:5173"

    # 数据库
    database_url: str = "postgresql+asyncpg://humanpulse:humanpulse@localhost:5432/humanpulse"

    # LLM（Phase 1 起使用）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model_bulk: str = "deepseek-chat"
    llm_model_brief: str = "deepseek-reasoner"
    llm_daily_token_budget: int = 2_000_000

    # 流水线（Phase 1 起使用）
    store_fulltext: bool = False
    simhash_hamming_threshold: int = Field(default=3, ge=0, le=32)
    vector_dup_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    vector_dup_threshold_hot: float = Field(default=0.80, ge=0.0, le=1.0)
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # 采集
    collector_user_agent: str = "humanpulse/0.1 (+https://github.com/sqhc/humanpulse)"
    http_proxy: str = ""

    # 简报
    brief_timezone: str = "UTC"
    brief_daily_cron: str = "0 6 * * *"

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _guard_prod_secrets(self) -> Settings:
        if self.is_prod and self.admin_api_key in INSECURE_DEFAULTS:
            raise ValueError("生产环境必须设置 ADMIN_API_KEY（不能使用默认值）")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
