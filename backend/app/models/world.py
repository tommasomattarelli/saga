"""ADR 0008 — world meta-schema (P0) + authored entity models.

Pydantic models for the World asset: the taxonomy (world-defined vocabularies),
the generic node, and the authored collections (edges, encounters, factions,
NPCs, scenario). Params are validated dynamically against the taxonomy by
`core/world_validator.py`, not here.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.npc_class import NpcClassDef
from app.models.npc_fields import NpcFieldDef
from app.models.psychology import PsychologyDef

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
DICE_PATTERN = r"^\d+d\d+([+-]\d+)?$"

ParamValue = int | float | str | bool


class ParamDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["int", "float", "str", "bool"] = "str"
    required: bool = False
    min: float | None = None
    max: float | None = None


class KindDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    scale: Literal["outdoor", "interior"]
    params: list[ParamDef] = []

    @field_validator("params")
    @classmethod
    def _unique_param_names(cls, params: list[ParamDef]) -> list[ParamDef]:
        names = [p.name for p in params]
        if len(names) != len(set(names)):
            raise ValueError("duplicate param names in kind definition")
        return params


class TerrainDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    travel_multiplier: float = Field(gt=0)


class TravelModeDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    speed_kmh: float = Field(gt=0)


class TaxonomyDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terrain: str | None = None
    elevation_m: float = 0


class Taxonomy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kinds: list[KindDef] = Field(min_length=1)
    terrains: list[TerrainDef] = []
    travel_modes: list[TravelModeDef] = []
    defaults: TaxonomyDefaults = TaxonomyDefaults()
    # ADR 0005: optional world-defined psychology axes; None → bundled default.
    psychology: PsychologyDef | None = None
    # ADR 0009: optional world-defined NPC descriptive fields; None → bundled default.
    npc_fields: list[NpcFieldDef] | None = None
    # ADR 0003 B3b: optional world-defined NPC classes; None → bundled default.
    npc_classes: list[NpcClassDef] | None = None

    @model_validator(mode="after")
    def _check_uniqueness_and_defaults(self) -> "Taxonomy":
        for label, names in [
            ("kind", [k.name for k in self.kinds]),
            ("terrain", [t.name for t in self.terrains]),
            ("travel_mode", [m.name for m in self.travel_modes]),
            ("npc_field", [f.name for f in self.npc_fields or []]),
            ("npc_class", [c.name for c in self.npc_classes or []]),
        ]:
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {label} names in taxonomy")
        if self.defaults.terrain is not None and self.terrain(self.defaults.terrain) is None:
            raise ValueError(f"default terrain '{self.defaults.terrain}' not in terrains")
        return self

    def kind(self, name: str) -> KindDef | None:
        return next((k for k in self.kinds if k.name == name), None)

    def terrain(self, name: str) -> TerrainDef | None:
        return next((t for t in self.terrains if t.name == name), None)

    def mode(self, name: str) -> TravelModeDef | None:
        return next((m for m in self.travel_modes if m.name == name), None)

    def npc_field(self, name: str) -> NpcFieldDef | None:
        return next((f for f in self.npc_fields or [] if f.name == name), None)

    def npc_class(self, name: str) -> NpcClassDef | None:
        return next((c for c in self.npc_classes or [] if c.name == name), None)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class ExitDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str
    locked: bool = False
    hidden: bool = False
    notes: str | None = None


class ItemDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    qty: int = Field(default=1, ge=1)
    notes: str | None = None


class WorldNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SLUG_PATTERN)
    kind: str
    name: str
    description: str = ""
    position: Position | None = None
    elevation_m: float | None = None
    terrain: str | None = None
    km_per_unit: float = Field(default=1.0, gt=0)
    map_image: str | None = None  # reserved (B4) — authored map images are post-v1
    params: dict[str, ParamValue] = {}
    items: list[ItemDef] = []
    exits: list[ExitDef] = []


class EdgeDef(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    slug: str = Field(pattern=SLUG_PATTERN)
    from_: str = Field(alias="from")
    to: str
    mode: str
    terrain: str | None = None
    travel_time: float | None = Field(default=None, gt=0)  # hours, authored override
    distance_km: float | None = Field(default=None, gt=0)
    encounter_table: str | None = None
    encounter_chance: float | None = Field(default=None, ge=0, le=1)
    conditions: list[str] = []
    directed: bool = False


class EncounterEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roll: tuple[int, int]
    type: Literal["event", "combat"]
    description: str
    once: bool = False

    @field_validator("roll")
    @classmethod
    def _min_le_max(cls, roll: tuple[int, int]) -> tuple[int, int]:
        if roll[0] > roll[1]:
            raise ValueError("roll range min must be <= max")
        return roll


class EncounterTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SLUG_PATTERN)
    dice: str = Field(pattern=DICE_PATTERN)
    entries: list[EncounterEntry] = Field(min_length=1)


class FactionRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: int = Field(ge=-10, le=10)
    label: str = ""


class ReputationTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: int
    label: str
    perks: list[str] = []
    penalties: list[str] = []


class ResourceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    quantity: float
    notes: str | None = None


class FactionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SLUG_PATTERN)
    name: str
    description: str = ""
    goals: list[str] = []
    relations: dict[str, FactionRelation] = {}
    reputation_tiers: list[ReputationTier] = []
    resources: list[ResourceDef] = []


class NpcRecord(BaseModel):
    """Engine-authored NPC fields; descriptives are world-defined (ADR 0009 G1/G4).

    Extra keys are the flat-authored descriptive fields — collected via
    `descriptives()` and tier-3-validated against the taxonomy's `npc_fields`.
    """

    model_config = ConfigDict(extra="allow")

    slug: str = Field(pattern=SLUG_PATTERN)
    name: str
    location: str | None = None
    psychology: dict[str, int] = {}
    faction: str | None = None

    def descriptives(self) -> dict[str, str]:
        return dict(self.model_extra or {})


class InitialQuest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    objectives: list[str] = []


class StoryArc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    trigger: str = ""
    description: str = ""


class Opening(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narration: str
    start_location: str
    time_of_day: str = ""
    weather: str = ""


class ScenarioDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening: Opening
    initial_quests: list[InitialQuest] = []
    story_arcs: list[StoryArc] = []
    dm_persona: str | None = None


class WorldMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    author: str = ""
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = []


class WorldRootFile(BaseModel):
    """Shape of `world.yaml`: the meta block + the root node's own fields."""

    model_config = ConfigDict(extra="forbid")

    meta: WorldMeta
    kind: str
    description: str = ""
    km_per_unit: float = Field(default=1.0, gt=0)
    elevation_m: float | None = None
    terrain: str | None = None
    map_image: str | None = None
    params: dict[str, ParamValue] = {}
    items: list[ItemDef] = []


def is_valid_slug(value: str) -> bool:
    return re.fullmatch(SLUG_PATTERN, value) is not None
