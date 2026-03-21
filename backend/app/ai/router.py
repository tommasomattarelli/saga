"""AI model router - selects the best model per call based on scene importance."""

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
    """Load model config from YAML, cached after first read."""
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _cfg_to_model_config(cfg: dict) -> ModelConfig:
    """Convert a YAML config dict to a ModelConfig dataclass."""
    return ModelConfig(
        provider=cfg["provider"],
        model=cfg["model"],
        temperature=float(cfg.get("temperature", 0.8)),
        max_tokens=int(cfg.get("max_tokens", 2000)),
    )


def _get_config_for_call(call_type: AICallType, tier: str = "default") -> ModelConfig:
    """Resolve a ModelConfig with a three-level override hierarchy.

    Priority (highest → lowest):
    1. Specific env-var override: ``SAGA_MODEL_{CALL_TYPE}_{TIER}``
       e.g. ``SAGA_MODEL_DM_NARRATION_HIGH=gpt-4o``
       Overrides model name only; provider stays from YAML or global.

    2. Global env-var overrides (set in ``.env``):
       - ``SAGA_GLOBAL_PROVIDER`` → applies the same provider to every call.
       - ``SAGA_GLOBAL_MODEL_HIGH/MEDIUM/LOW`` → sets the model for that tier.
       Use this to switch to "Gemini for everything" or "OpenAI for everything"
       without touching YAML files.

    3. ``model_config.yaml`` defaults — the base configuration shipped with
       the project.
    """
    config = _load_config()
    key = call_type.value  # e.g. "dm_narration"
    tier_cfg = config.get(key, {}).get(tier) or config.get(key, {}).get("default", {})
    model_config = _cfg_to_model_config(tier_cfg)

    global_provider = settings.saga_global_provider.strip()
    if global_provider:
        model_config.provider = global_provider

    global_model_by_tier: dict[str, str] = {
        "high":   settings.saga_global_model_high.strip(),
        "medium": settings.saga_global_model_medium.strip(),
        "low":    settings.saga_global_model_low.strip(),
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


async def route_ai_call(call_type: AICallType, context: "GameContext") -> ModelConfig:  # noqa: F821
    """Select the appropriate model based on call type and context importance.

    For DM narration, routes based on importance score (from GameContext):
    - 0-3:  low    tier (budget model — background events, simple responses)
    - 4-6:  medium tier (standard model — normal gameplay)
    - 7-10: high   tier (premium model — boss fights, dramatic reveals)

    All other call types use their single "default" tier.

    Override hierarchy (set in .env):
    1. ``SAGA_MODEL_{CALL_TYPE}_{TIER}``       — per-call model override
    2. ``SAGA_GLOBAL_PROVIDER``                — single provider for everything
       ``SAGA_GLOBAL_MODEL_HIGH/MEDIUM/LOW``   — global model per tier
    3. ``model_config.yaml``                   — project defaults
    """
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
