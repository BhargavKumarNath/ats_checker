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
    # Layer 2 retrieval embeddings (self-hosted, ONNX). Larger than Layer 1's model because
    # latency tolerance is high; see build_plan.md Phase 8 for why not Qwen3/bge-m3.
    deep_embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Layer 1 web process.
    max_upload_bytes: int = 2_000_000  # resume files above this are refused with a 413
    warm_on_start: bool = True  # load the embedding model in the lifespan, not on first request
    # Per-client sliding-window limit on POST /score (atsc.web.ratelimit). 0 disables it.
    score_rate_limit: int = 30
    score_rate_window_seconds: int = 600
    # Header a trusted reverse proxy sets with the real client address ("Fly-Client-IP" on
    # Fly). Empty = use the socket peer. Never set this when clients can reach the app directly.
    client_ip_header: str = ""

    # Layer 2 persistence and delivery (build_plan.md §3: Postgres in production, SQLite locally).
    database_url: str = "sqlite:///./atsc.db"
    public_base_url: str = "http://127.0.0.1:8000"  # used in Stripe redirect URLs and emails

    # Stripe Checkout, one-time payment (product_requirements.md §3: never a subscription).
    # All three must be set for the paid path to be offered; otherwise the CTA explains it is off.
    stripe_secret_key: str = ""
    stripe_price_id: str = ""
    stripe_webhook_secret: str = ""

    # Report link email. Unset SMTP host = links are logged, not sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""

    # Taxonomy growth loop (gap_analysis_spec.md §4). Empty = off. When set, unmatched skill
    # terms are counted in aggregate in this SQLite file; see atsc.free.growth.
    growth_log_path: str = ""

    # Worker polling interval in seconds.
    worker_poll_seconds: float = 3.0

    @property
    def payments_enabled(self) -> bool:
        return bool(self.stripe_secret_key and self.stripe_price_id and self.stripe_webhook_secret)


def get_settings() -> Settings:
    return Settings()
