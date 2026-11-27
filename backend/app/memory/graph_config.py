from __future__ import annotations

from pydantic import Field, model_validator

from app.config_loader import load_saga_config
from app.memory.production_policy import _PolicyModel


class RelationKindConfig(_PolicyModel):
    kind: str = Field(min_length=1)
    prominent: bool = False
    description: str = ""


class GraphConfig(_PolicyModel):
    max_relations: int = Field(default=200, ge=1)
    prominent_max_relations: int = Field(default=12, ge=0)
    scene_max_relations: int = Field(default=20, ge=0)
    faction_max_relations: int = Field(default=8, ge=0)
    extract_max_per_batch: int = Field(default=8, ge=0)
    default_relation_kinds: list[RelationKindConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounded_slots(self) -> GraphConfig:
        if self.prominent_max_relations > self.max_relations:
            raise ValueError(
                "saga.config.yaml: graph.prominent_max_relations exceeds max_relations"
            )
        if self.scene_max_relations > self.max_relations:
            raise ValueError("saga.config.yaml: graph.scene_max_relations exceeds max_relations")
        if self.faction_max_relations > self.max_relations:
            raise ValueError("saga.config.yaml: graph.faction_max_relations exceeds max_relations")
        if self.extract_max_per_batch > self.max_relations:
            raise ValueError("saga.config.yaml: graph.extract_max_per_batch exceeds max_relations")
        kinds = [kind.kind for kind in self.default_relation_kinds]
        if len(set(kinds)) != len(kinds):
            raise ValueError("saga.config.yaml: graph.default_relation_kinds repeats a kind")
        return self


def get_graph_config() -> GraphConfig:
    return GraphConfig.model_validate(load_saga_config().get("graph", {}))
