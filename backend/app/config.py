from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_version: str = "0.1.0"

    database_url: str = "postgresql+asyncpg://saga:saga@localhost:5432/saga"

    jwt_secret: str = "change-me-to-a-random-256-bit-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30
    api_key_encryption_key: str = "change-me-to-a-random-256-bit-key"

    saga_environment: Literal["dev", "prod", "test"] = "dev"

    # Path to the built frontend (dist/). Set only by the native installer so the
    # backend serves the SPA itself; empty in dev/Docker, where Vite serves it.
    saga_frontend_dist: str = ""

    @model_validator(mode="after")
    def _validate_secrets_in_prod(self) -> "Settings":
        if self.saga_environment != "prod":
            return self
        insecure = [
            name
            for name, value in [
                ("jwt_secret", self.jwt_secret),
                ("api_key_encryption_key", self.api_key_encryption_key),
            ]
            if value.startswith("change-me")
        ]
        if insecure:
            raise ValueError(
                f"Insecure default values detected in prod for: {', '.join(insecure)}. "
                "Set proper secrets via environment variables."
            )
        return self

    openai_api_key: str = ""
    # Accept legacy .env entries without restoring the retired provider.
    anthropic_api_key: str = ""
    google_ai_api_key: str = ""

    local_model_url: str = "http://localhost:8080/v1"
    openrouter_api_key: str = ""

    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
