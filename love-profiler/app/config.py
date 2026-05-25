"""
Centralized configuration via pydantic BaseSettings.

All environment variables in one place; startup-time validation and type conversion.
Import: `from app.config import settings`

settings is a proxy that creates a fresh Settings() on each attribute access,
so monkeypatch.setenv in tests takes effect without cache invalidation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


import os

_env_file = ".env" if os.environ.get("_TESTING") != "1" else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    dev_mode: bool = False
    database_url: str = "sqlite:///./love_profiler.db"
    jwt_secret: str = ""

    cors_origins: str = ""
    admin_token: str = ""

    douyin_app_id: str = ""
    douyin_app_secret: str = ""
    douyin_pay_token: str = ""
    douyin_ad_secret: str = ""

    doubao_api_key: str = ""
    doubao_model: str = ""
    ai_log_path: str = ""

    judge_enabled: bool = False
    judge_model: str = ""

    resume_enabled: bool = True
    user_daily_token_quota: int = 20_000

    @property
    def cors_origins_list(self) -> list[str]:
        if self.dev_mode:
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


class _SettingsProxy:
    """Proxy that creates a fresh Settings() on every attribute access."""
    __slots__ = ()

    def __getattr__(self, name: str):
        return getattr(Settings(), name)


settings = _SettingsProxy()
