"""Runtime configuration. The only place environment variables are read.

All settings are prefixed ATSC_. The Layer 1 web process must run without
ANTHROPIC_API_KEY in its environment (cost boundary, guard 3); the Layer 2
worker is the only process that needs it, and the Anthropic SDK reads it
directly, so it is deliberately not modelled here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATSC_", env_file=".env", extra="ignore")

    # Layer 2 runtime LLM. Owner decision 2026-09-15: sonnet-5 by default, never hardcoded.
    deep_llm_model: str = "claude-sonnet-5"

    # Layer 1 web process.
    max_upload_bytes: int = 2_000_000  # resume files above this are refused with a 413
    warm_on_start: bool = True  # load the embedding model in the lifespan, not on first request


def get_settings() -> Settings:
    return Settings()
