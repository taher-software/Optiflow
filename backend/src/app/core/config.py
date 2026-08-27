from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Frontend URL used to build the email-confirmation link.
    frontend_url: str = "http://localhost:5173/"

    # Resend (transactional email).
    resend_api_key: str = ""
    email_from: str = "bodor@bodor.tn"

    # Security — signs the email-confirmation and access tokens.
    secret_key: str = "change-me-in-production"
    confirm_token_max_age_seconds: int = 60 * 60 * 24  # 24 hours
    access_token_max_age_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Root logging level. Nothing configures logging otherwise, so every
    # `logger.info(...)` in the codebase is dropped and warnings only escape
    # through logging's last-resort handler — see `main._configure_logging`.
    log_level: str = "INFO"

    # GCP — backs Pub/Sub topics and Cloud Tasks queues.
    google_project_id: str = ""
    # Cloud Tasks target: base URL of the worker service (task is POSTed to
    # `{worker_url}/cloud_job`).
    worker_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
