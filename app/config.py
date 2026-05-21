from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "Bambu Fleet Manager"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── Security ─────────────────────────────────────────────────────────────
    secret_key: str = Field(..., min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(...)
    # Async variant: postgresql+asyncpg://user:pass@host/db
    # The env var should already include +asyncpg

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ── File storage ──────────────────────────────────────────────────────────
    upload_dir: str = "/tmp/bambu_uploads"
    max_upload_size_mb: int = 500

    # ── Bambu Lab MQTT ────────────────────────────────────────────────────────
    # Per-printer credentials are stored in the DB, but we need global MQTT
    # broker settings (Bambu cloud vs local).
    bambu_mqtt_host: str = "us.mqtt.bambulab.com"
    bambu_mqtt_port: int = 8883           # TLS port
    bambu_mqtt_use_tls: bool = True

    # ── Monitoring ────────────────────────────────────────────────────────────
    status_poll_interval_seconds: int = 30
    job_timeout_seconds: int = 86400      # 24 h max job time

    @field_validator("database_url")
    @classmethod
    def must_be_async_postgres(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+asyncpg' scheme. "
                "Example: postgresql+asyncpg://user:pass@postgres/bambu"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — called once per process."""
    return Settings()