"""Single pydantic-settings Settings object — never scatter os.getenv in modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # core
    recoup_env: Literal["local", "ci", "staging", "production"] = "local"
    recoup_seed: int = 42
    log_level: str = "INFO"

    # datastores
    database_url: str = "postgresql+asyncpg://recoup:recoup@localhost:5432/recoup"
    redis_url: str = "redis://localhost:6379/0"

    # razorpay (test mode only)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_mode: Literal["test", "live"] = "test"

    # anthropic
    anthropic_api_key: str = ""
    anthropic_model_fast: str = "claude-sonnet-4-5"
    anthropic_model_deep: str = "claude-opus-4-5"
    llm_timeout_seconds: int = 8
    llm_redaction_enabled: bool = True

    # groq — grounded Q&A's drafter only (see docs/adr/0009-groq-grounded-qa.md);
    # every other LLM path stays on Anthropic above
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # channels
    channel_mode: Literal["simulator", "live"] = "simulator"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    resend_api_key: str = ""

    # recovery links
    link_signing_secret: str = "change-me"
    link_ttl_hours: int = 72
    public_base_url: str = "http://localhost:3000"

    # policy / governance
    policy_dir: str = "./policies"
    merchant_id: str = "demo"
    kill_switch: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
