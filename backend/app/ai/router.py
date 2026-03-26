from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import settings


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


# Path to the YAML config file
_CONFIG_PATH = Path(__file__).parent / "model_config.yaml"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


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
    global_model = global_model_by_tier.get(tier, "")
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
    """Runtime gameplay settings loaded from model_config.yaml."""

    context_window_turns: int = 8
    npc_verbosity: str = "medium"
    compression_enabled: bool = True
    fact_extraction_enabled: bool = True

    @property
    def max_npc_calls(self) -> int:
        return _NPC_VERBOSITY_MAP.get(self.npc_verbosity, 3)


def get_gameplay_config() -> GameplayConfig:
    """Read the gameplay section from model_config.yaml with env overrides."""
    config = _load_config()
    gp = config.get("gameplay", {})

    ctx_turns = int(os.getenv("SAGA_GAMEPLAY_CONTEXT_WINDOW_TURNS", gp.get("context_window_turns", 8)))
    verbosity = os.getenv("SAGA_GAMEPLAY_NPC_VERBOSITY", gp.get("npc_verbosity", "medium"))
    compression = os.getenv("SAGA_GAMEPLAY_COMPRESSION_ENABLED", str(gp.get("compression_enabled", True)))
    fact_ext = os.getenv("SAGA_GAMEPLAY_FACT_EXTRACTION_ENABLED", str(gp.get("fact_extraction_enabled", True)))

    return GameplayConfig(
        context_window_turns=ctx_turns,
        npc_verbosity=verbosity,
        compression_enabled=compression.lower() not in ("false", "0", "no"),
        fact_extraction_enabled=fact_ext.lower() not in ("false", "0", "no"),
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
