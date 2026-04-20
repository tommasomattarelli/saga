from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from app.config import settings
from app.config_loader import load_saga_config


class AICallType(StrEnum):
    """Types of AI calls with different routing strategies."""

    DM_NARRATION = "dm_narration"
    COMPANION_DIALOGUE = "companion_dialogue"
    NPC_BEHAVIOR = "npc_behavior"
    WORLD_SIM = "world_sim"
    MEMORY_COMPRESSION = "memory_compression"
    EMBEDDING = "embedding"


@dataclass
class ModelConfig:
    """Selected model configuration for an AI call."""

    provider: str
    model: str
    temperature: float
    max_tokens: int


def _load_config() -> dict:
    return load_saga_config()


def _cfg_to_model_config(cfg: dict) -> ModelConfig:
    return ModelConfig(
        provider=cfg["provider"],
        model=cfg["model"],
        temperature=float(cfg.get("temperature", 0.8)),
        max_tokens=int(cfg.get("max_tokens", 2000)),
    )


def _get_config_for_call(call_type: AICallType, tier: str = "default") -> ModelConfig:
    """Resolve a ModelConfig with a three-level override hierarchy."""
    config = _load_config()
    key = call_type.value  # e.g. "dm_narration"
    tier_cfg = config.get(key, {}).get(tier) or config.get(key, {}).get("default", {})
    model_config = _cfg_to_model_config(tier_cfg)

    global_provider = settings.saga_global_provider.strip()
    if global_provider:
        model_config.provider = global_provider

    global_model_by_tier: dict[str, str] = {
        "high": settings.saga_global_model_high.strip(),
        "medium": settings.saga_global_model_medium.strip(),
        "low": settings.saga_global_model_low.strip(),
    }
    # "default" tier (background tasks) falls back to medium, then low, then high
    global_model = global_model_by_tier.get(tier, "") or (
        global_model_by_tier.get("medium", "")
        or global_model_by_tier.get("low", "")
        or global_model_by_tier.get("high", "")
        if global_provider
        else ""
    )
    if global_model:
        model_config.model = global_model

    specific_env_key = f"SAGA_MODEL_{call_type.value.upper()}_{tier.upper()}"
    specific_model = os.getenv(specific_env_key, "").strip()
    if specific_model:
        model_config.model = specific_model

    specific_provider_env_key = f"{specific_env_key}_PROVIDER"
    specific_provider = os.getenv(specific_provider_env_key, "").strip()
    if specific_provider:
        model_config.provider = specific_provider

    return model_config


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
        npc_verbosity=os.getenv(
            "SAGA_GAMEPLAY_NPC_VERBOSITY", gp.get("npc_verbosity", "medium")
        ),
        compression_enabled=_bool_env(
            "SAGA_GAMEPLAY_COMPRESSION_ENABLED", gp.get("compression_enabled", True)
        ),
        fact_extraction_enabled=_bool_env(
            "SAGA_GAMEPLAY_FACT_EXTRACTION_ENABLED", gp.get("fact_extraction_enabled", True)
        ),
        global_summary_enabled=_bool_env(
            "SAGA_GLOBAL_SUMMARY_ENABLED", gs.get("enabled", True)
        ),
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
    )


def get_summarization_config() -> SummarizationConfig:
    """Read the summarization section from saga.config.yaml."""
    config = _load_config()
    sc = config.get("summarization", {})

    return SummarizationConfig(
        max_retries=int(os.getenv("SAGA_SUMMARIZATION_MAX_RETRIES", sc.get("max_retries", 3))),
        retry_delays_seconds=sc.get("retry_delays_seconds", [1, 5, 30]),
    )


async def route_ai_call(call_type: AICallType, context: GameContext) -> ModelConfig:  # noqa: F821
    """Select the appropriate model based on call type and context importance."""
    if call_type == AICallType.DM_NARRATION:
        importance = getattr(context, "importance_score", 5)
        if importance <= 3:
            tier = "low"
        elif importance <= 6:
            tier = "medium"
        else:
            tier = "high"
        return _get_config_for_call(call_type, tier)

    return _get_config_for_call(call_type, "default")
