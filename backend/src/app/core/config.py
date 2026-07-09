from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Frontend URL used to build the email-confirmation link.
    frontend_url: str = "http://localhost:5173/"

    # Resend (transactional email).
    resend_api_key: str = ""
    email_from: str = "OptiFlow <onboarding@optiflow.app>"

    # Security — signs the email-confirmation token.
    secret_key: str = "change-me-in-production"
    confirm_token_max_age_seconds: int = 60 * 60 * 24  # 24 hours


@lru_cache
def get_settings() -> Settings:
    return Settings()
