"""AI model router - selects the best model per call based on scene importance."""

from dataclasses import dataclass
from enum import StrEnum

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


# Default routing table
ROUTING_TABLE: dict[AICallType, list[ModelConfig]] = {
    AICallType.DM_NARRATION: [
        # Low importance (0-3): budget model
        ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.8, max_tokens=2000),
        # Medium importance (4-6): standard model
        ModelConfig(provider="openai", model="gpt-4o", temperature=0.8, max_tokens=3000),
        # High importance (7-10): premium model
        ModelConfig(provider="openai", model="gpt-4o", temperature=0.9, max_tokens=4000),
    ],
    AICallType.COMPANION_DIALOGUE: [
        ModelConfig(provider="google", model="gemini-2.5-pro", temperature=0.7, max_tokens=1500),
    ],
    AICallType.NPC_BEHAVIOR: [
        ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=1000),
    ],
    AICallType.WORLD_SIM: [
        ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.5, max_tokens=1500),
    ],
    AICallType.MEMORY_COMPRESSION: [
        ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.3, max_tokens=500),
    ],
}


async def route_ai_call(call_type: AICallType, context: "GameContext") -> ModelConfig:  # noqa: F821
    """Select the appropriate model based on call type and context importance.

    For DM narration, routes based on importance score:
    - 0-3: budget model (background events, simple responses)
    - 4-6: standard model (normal gameplay)
    - 7-10: premium model (boss fights, dramatic reveals, key story moments)
    """
    configs = ROUTING_TABLE.get(call_type, ROUTING_TABLE[AICallType.NPC_BEHAVIOR])

    if call_type == AICallType.DM_NARRATION and len(configs) >= 3:
        importance = getattr(context, "importance_score", 5)
        if importance <= 3:
            return configs[0]
        elif importance <= 6:
            return configs[1]
        else:
            return configs[2]

    return configs[0]
