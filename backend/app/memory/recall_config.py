from __future__ import annotations

from pydantic import Field, model_validator

from app.config_loader import load_saga_config
from app.memory.production_policy import _PolicyModel


class RecallQueryConfig(_PolicyModel):
    include_scene: bool = True
    recent_narration_turns: int = Field(default=2, ge=0)
    anchor_max_chars: int = Field(default=200, ge=1)


class RecallBoostsConfig(_PolicyModel):
    entity_canonical_ref: float = Field(default=0.0, ge=0)
    entity_name: float = Field(default=0.0, ge=0)
    critical: float = Field(default=0.0, ge=0)
    recency_tiebreak: float = Field(default=0.0, ge=0)


class RecallDedupConfig(_PolicyModel):
    enabled: bool = True
    similarity_threshold: float = Field(default=1.0, ge=0, le=1)


class RecallConfig(_PolicyModel):
    enabled: bool = True
    candidate_pool: int = Field(default=25, ge=1)
    inject_limit: int = Field(default=5, ge=1)
    rrf_k: int = Field(default=60, ge=0)
    critical_always_include: bool = False
    max_critical_inject: int = Field(default=5, ge=0)
    query: RecallQueryConfig = RecallQueryConfig()
    boosts: RecallBoostsConfig = RecallBoostsConfig()
    dedup: RecallDedupConfig = RecallDedupConfig()

    @model_validator(mode="after")
    def _bounded_slots(self) -> RecallConfig:
        if self.inject_limit > self.candidate_pool:
            raise ValueError("saga.config.yaml: recall.inject_limit exceeds candidate_pool")
        if self.max_critical_inject > self.inject_limit:
            raise ValueError("saga.config.yaml: recall.max_critical_inject exceeds inject_limit")
        return self


def get_recall_config() -> RecallConfig:
    return RecallConfig.model_validate(load_saga_config().get("recall", {}))
