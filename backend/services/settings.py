"""Typed application settings for local and production runtime."""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    database_url: str = ""

    openai_api_key: str = ""
    openai_resume_parse_model: str = "gpt-5.4"
    resume_parse_dpi: int = 200
    resume_parse_image_detail: str = "high"
    resume_parse_max_file_size_bytes: int = 10 * 1024 * 1024
    resume_parse_item_concurrency: int = 5
    resume_parse_page_concurrency: int = 4
    resume_parse_request_retries: int = 2

    clerk_secret_key: str = ""
    clerk_invite_redirect_url: str = "https://app.growqr.ai/login"
    clerk_invite_notify: bool = True
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    clerk_webhook_secret: str = ""

    auth_allow_local_headers: bool = False
    api_cors_origins: str = ""
    api_max_request_body_bytes: int = 15 * 1024 * 1024

    storage_backend: str = "local"
    local_storage_root: str = ".local_storage"
    s3_bucket_name: str = ""
    s3_region: str = ""
    s3_prefix: str = "growqr-admin"
    s3_presigned_url_ttl_seconds: int = 900

    queue_backend: str = "local"
    local_queue_root: str = ".local_queue"
    sqs_resume_upload_queue_url: str = ""
    sqs_region: str = ""
    queue_receive_max_messages: int = 5
    queue_wait_time_seconds: int = 10
    worker_poll_interval_seconds: float = 2.0

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
