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

    # LLM（模型名以 GET /models 实测为准，见 .env.example 注释）
    llm_provider: str = "deepseek"  # deepseek | fake
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_model_bulk: str = "deepseek-flash"
    llm_model_brief: str = "deepseek-v4-pro"
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_daily_token_budget: int = 2_000_000
    # 单批并发调用数：5 条串行约 5.4s/条，并发后吞吐显著提升
    llm_concurrency: int = Field(default=5, gt=0, le=20)

    # 流水线
    store_fulltext: bool = False
    simhash_hamming_threshold: int = Field(default=3, ge=0, le=32)
    vector_dup_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    vector_dup_threshold_hot: float = Field(default=0.80, ge=0.0, le=1.0)
    vector_dup_window_hours: int = Field(default=24, gt=0)
    # hash = 无需下载模型的确定性向量（开发/CI 用，语义能力弱）
    # local = sentence-transformers 多语种模型（生产用，需安装 ml 额外依赖）
    embedding_provider: str = "hash"  # hash | local
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = Field(default=384, gt=0)

    # 采集
    collector_user_agent: str = "humanpulse/0.1 (+https://github.com/sqhc/humanpulse)"
    http_proxy: str = ""
    collector_timeout_seconds: float = Field(default=20.0, gt=0)
    rss_max_items_per_feed: int = Field(default=30, gt=0)
    gdelt_max_records: int = Field(default=75, gt=0)
    # 一条内容比这个天数还旧就不进 Feed（防止过期/静态 XML 混进来）
    max_item_age_days: int = Field(default=45, gt=0)
    # GDELT 实际比文档更严格（实测 6s 仍会 429），留出余量
    gdelt_throttle_seconds: float = Field(default=12.0, ge=0)
    uploads_dir: str = "uploads"
    max_upload_mb: int = Field(default=25, gt=0)

    # 后台 worker（内置间隔调度）
    collect_interval_minutes: int = Field(default=30, gt=0)
    process_interval_minutes: int = Field(default=2, gt=0)
    process_batch_size: int = Field(default=20, gt=0)

    # 旁白语音合成（视频简报用）。none = 不做配音（默认）。
    # macos-say 只在本机开发可用；生产 Linux 用 command 模板接 piper / edge-tts / 云 TTS。
    tts_provider: str = "none"
    tts_voice: str = "Tingting"
    tts_command: str = ""

    # 视频配色：light = 浅色编辑风（对照排版参考截屏，默认）；dark = 旧深色
    video_theme: str = "light"

    # 判官模型（推演用）：输出类型化决策与概率，不生成文本。
    # none = 不做推演；fake = 确定性假实现（CI）；laya = 本地 Laya；jev = 云端 TypeSafe。
    # laya 与 jev 共用同一套请求协议，只差 base_url（本地 serve.py 暴露 Jev 兼容路由）。
    judgement_provider: str = "none"
    judgement_base_url: str = "http://127.0.0.1:8077"
    judgement_api_key: str = ""
    judgement_model: str = "laya-multilingual"
    judgement_timeout_seconds: float = Field(default=30.0, gt=0)
    # 本地 Laya serve 脚本位置（cookbook 的 serve.py）；留空则用环境变量 LAYA_SERVE_SCRIPT
    judgement_serve_script: str = ""
    # Laya multilingual 上下文上限 1024 token，state 留出余量
    judgement_max_state_tokens: int = Field(default=900, gt=100)

    # 推演（链路式后果分析）
    projection_enabled: bool = False
    projection_max_events: int = Field(default=3, ge=1, le=10)
    projection_horizon_days: int = Field(default=14, ge=1, le=180)
    # 低于此置信度的节点不进视频断言，只标为「待观察」
    projection_min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    projection_chain_hops: int = Field(default=3, ge=1, le=5)

    # 实体别名裁决（用判官做实体对齐）
    alias_adjudication_enabled: bool = False
    alias_auto_merge_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    entity_wikidata_enabled: bool = False

    # 简报
    # 日报：几点生成、时间窗多长、最多选多少条素材（同一 cluster 只留一条代表）
    brief_hour: int = Field(default=6, ge=0, le=23)
    # 周报在每周的哪一天生成（0=周一 … 6=周日）
    brief_weekday: int = Field(default=6, ge=0, le=6)
    brief_lookback_hours: int = Field(default=24, gt=0, le=168)
    brief_top_items: int = Field(default=12, gt=0, le=40)
    # 周报：窗口天数与素材上限（趋势数字由 SQL 算好，不靠模型）
    weekly_lookback_days: int = Field(default=7, gt=0, le=31)
    weekly_top_items: int = Field(default=20, gt=0, le=60)

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
