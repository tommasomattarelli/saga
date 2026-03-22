from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://saga:saga@localhost:5432/saga"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-random-256-bit-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30
    api_key_encryption_key: str = "change-me-to-a-random-256-bit-key"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""

    # Set SAGA_GLOBAL_PROVIDER to use a single provider for everything.
    # Set SAGA_GLOBAL_MODEL_* to define the three reasoning tiers globally.
    # Fine-grained per-call overrides (SAGA_MODEL_DM_NARRATION_HIGH etc.) still
    # take precedence over these globals.
    saga_global_provider: str = ""  # e.g. "google", "openai", "anthropic"
    saga_global_model_high: str = ""  # premium model — boss fights, dramatic moments
    saga_global_model_medium: str = ""  # standard model — normal gameplay
    saga_global_model_low: str = ""  # budget model  — background tasks, simple actions

    app_mode: str = "community"
    default_language: str = "en"
    telemetry_enabled: bool = False
    log_level: str = "info"

    cloudflare_r2_access_key: str = ""
    cloudflare_r2_secret_key: str = ""
    cloudflare_r2_bucket: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
