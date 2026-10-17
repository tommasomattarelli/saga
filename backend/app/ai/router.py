"""Generation configuration — one model for every AI call (ADR 0018)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.config_loader import load_saga_config

PROVIDER_NAMES = ("openai", "openrouter", "google", "local")


@dataclass
class ModelConfig:
    """The provider/model pair a generation call runs on (ADR 0018 A1)."""

    provider: str
    model: str
    max_tokens: int


def _load_config() -> dict:
    return load_saga_config()


def get_instance_default() -> ModelConfig:
    """Provider and model a user inherits before configuring their own (ADR 0018 A6)."""
    generation = _load_config().get("generation", {})
    default = generation.get("default", {})
    cap = int(generation.get("max_output_tokens", 0) or 0)
    if cap <= 0:
        raise ValueError(
            "saga.config.yaml: generation.max_output_tokens must be a positive integer"
        )
    return ModelConfig(
        provider=str(default.get("provider", "")),
        model=str(default.get("model", "")),
        max_tokens=cap,
    )


def get_allowed_providers() -> list[str]:
    """Instance allowlist shared by generation and embeddings (ADR 0018 A5)."""
    allowed = _load_config().get("providers", {}).get("allowed", list(PROVIDER_NAMES))
    if isinstance(allowed, str) and allowed.strip().lower() == "all":
        return list(PROVIDER_NAMES)
    return [str(name) for name in allowed]


def get_server_key_fallback() -> dict[str, bool]:
    """Operator half of the double consent for server keys (ADR 0018 A4)."""
    raw = _load_config().get("providers", {}).get("server_key_fallback", {})
    return {str(provider): bool(enabled) for provider, enabled in raw.items()}


def get_local_endpoints() -> dict[str, str]:
    """Named local endpoints the backend may contact (ADR 0018 A5/B2)."""
    raw = _load_config().get("providers", {}).get("local_endpoints", {})
    return {
        str(name): str(config.get("base_url", ""))
        for name, config in raw.items()
        if isinstance(config, dict)
    }


def validate_generation_config() -> None:
    """Fail fast on an unusable generation or providers block (ADR 0018 A9)."""
    problems: list[str] = []
    generation = _load_config().get("generation")
    if not isinstance(generation, dict):
        problems.append("the generation block is missing")
    else:
        default = generation.get("default", {})
        provider = str(default.get("provider", "")).strip()
        model = str(default.get("model", "")).strip()
        cap = int(generation.get("max_output_tokens", 0) or 0)
        if provider not in get_allowed_providers():
            problems.append(
                f"generation.default.provider `{provider}` is not in providers.allowed"
            )
        if not model:
            problems.append("generation.default.model is empty")
        if cap <= 0:
            problems.append("generation.max_output_tokens must be a positive integer")
    for name, base_url in get_local_endpoints().items():
        if not base_url.startswith(("http://", "https://")):
            problems.append(f"providers.local_endpoints.{name}.base_url must be an http(s) URL")
    if problems:
        raise ValueError("saga.config.yaml (ADR 0018): " + "; ".join(problems))


_NPC_VERBOSITY_MAP: dict[str, int] = {
    "null": 0,
    "minimal": 1,
    "low": 2,
    "medium": 3,
    "high": 5,
    "unlimited": 999,
}


@dataclass
class GameplayConfig:
    """Runtime gameplay settings loaded from saga.config.yaml."""

    context_window_turns: int = 8
    context_token_cap: int = 12000
    npc_verbosity: str = "medium"
    compression_enabled: bool = True
    fact_extraction_enabled: bool = True
    global_summary_enabled: bool = True
    global_summary_update_every: int = 5
    pgvector_hybrid: bool = False
    auto_create_npcs: bool = True
    npc_auto_create_detail: str = "standard"
    consecutive_empty_steps_max: int = 2
    npc_last_interactions_kept: int = 3
    global_summary_max_input_chars: int = 4000
    npc_condition_max_chars: int = 80
    npc_name_match_threshold: float = 0.85

    @property
    def max_npc_calls(self) -> int:
        return _NPC_VERBOSITY_MAP.get(self.npc_verbosity, 3)


@dataclass
class SummarizationConfig:
    """Retry and deduplication settings for the summarization pipeline."""

    max_retries: int = 3
    retry_delays_seconds: list[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.retry_delays_seconds is None:
            self.retry_delays_seconds = [1, 5, 30]


def _bool_env(key: str, fallback: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return fallback
    return val.lower() not in ("false", "0", "no")


def get_gameplay_config() -> GameplayConfig:
    """Read the gameplay section from saga.config.yaml with env overrides."""
    config = _load_config()
    gp = config.get("gameplay", {})
    gs = config.get("features", {}).get("global_summary", {})

    return GameplayConfig(
        context_window_turns=int(
            os.getenv("SAGA_GAMEPLAY_CONTEXT_WINDOW_TURNS", gp.get("context_window_turns", 8))
        ),
        context_token_cap=int(
            os.getenv("SAGA_GAMEPLAY_CONTEXT_TOKEN_CAP", gp.get("context_token_cap", 12000))
        ),
        npc_verbosity=os.getenv("SAGA_GAMEPLAY_NPC_VERBOSITY", gp.get("npc_verbosity", "medium")),
        compression_enabled=_bool_env(
            "SAGA_GAMEPLAY_COMPRESSION_ENABLED", gp.get("compression_enabled", True)
        ),
        fact_extraction_enabled=_bool_env(
            "SAGA_GAMEPLAY_FACT_EXTRACTION_ENABLED", gp.get("fact_extraction_enabled", True)
        ),
        global_summary_enabled=_bool_env("SAGA_GLOBAL_SUMMARY_ENABLED", gs.get("enabled", True)),
        global_summary_update_every=int(
            os.getenv("SAGA_GLOBAL_SUMMARY_INTERVAL_TURNS", gs.get("interval_turns", 5))
        ),
        pgvector_hybrid=_bool_env(
            "SAGA_GAMEPLAY_PGVECTOR_HYBRID", gp.get("pgvector_hybrid", False)
        ),
        auto_create_npcs=_bool_env(
            "SAGA_GAMEPLAY_AUTO_CREATE_NPCS", gp.get("auto_create_npcs", True)
        ),
        npc_auto_create_detail=os.getenv(
            "SAGA_GAMEPLAY_NPC_AUTO_CREATE_DETAIL",
            gp.get("npc_auto_create_detail", "standard"),
        ),
        consecutive_empty_steps_max=int(
            os.getenv(
                "SAGA_GAMEPLAY_CONSECUTIVE_EMPTY_STEPS_MAX",
                gp.get("consecutive_empty_steps_max", 2),
            )
        ),
        npc_last_interactions_kept=int(
            os.getenv(
                "SAGA_GAMEPLAY_NPC_LAST_INTERACTIONS_KEPT",
                gp.get("npc_last_interactions_kept", 3),
            )
        ),
        global_summary_max_input_chars=int(
            os.getenv(
                "SAGA_GLOBAL_SUMMARY_MAX_INPUT_CHARS",
                gs.get("max_input_chars", 4000),
            )
        ),
        npc_condition_max_chars=int(
            os.getenv(
                "SAGA_GAMEPLAY_NPC_CONDITION_MAX_CHARS",
                gp.get("npc_condition_max_chars", 80),
            )
        ),
        npc_name_match_threshold=float(
            os.getenv(
                "SAGA_GAMEPLAY_NPC_NAME_MATCH_THRESHOLD",
                gp.get("npc_name_match_threshold", 0.85),
            )
        ),
    )


def get_summarization_config() -> SummarizationConfig:
    """Read the summarization section from saga.config.yaml."""
    config = _load_config()
    sc = config.get("summarization", {})

    return SummarizationConfig(
        max_retries=int(os.getenv("SAGA_SUMMARIZATION_MAX_RETRIES", sc.get("max_retries", 3))),
        retry_delays_seconds=sc.get("retry_delays_seconds", [1, 5, 30]),
    )
