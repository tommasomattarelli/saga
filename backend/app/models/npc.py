"""ADR 0009 — typed NPC engine contract + the B2 mutation partition.

Records stay dicts in the world_state JSONB; this model validates at the
boundaries (creation scaffold, update_npc). Descriptive fields live in
`traits`, whose keys are world-defined (taxonomy `npc_fields`).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Lifecycle = Literal["alive", "dead", "removed"]


class NpcEngineRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str | None = None  # authored alias; None = auto-created
    name: str
    lifecycle: Lifecycle = "alive"
    condition: str | None = None
    location: str | None = None  # world-node UUID (ADR 0008 J3)
    faction: str | None = None
    psychology: dict[str, int] = {}  # ADR 0005-owned
    met_player: bool = False  # ADR 0005-owned
    last_interactions: list[str] = []  # engine-owned dialogue log
    traits: dict[str, str] = {}  # world-defined descriptives

    # ADR 0003 B3 — statblock. None only between construction and the scaffold's
    # draw; every stored record carries concrete values (test-enforced).
    hp: int | None = None
    max_hp: int | None = None
    defense: str | None = None  # one of the six difficulty levels (A2), no second scale
    attack_mod: int | None = None
    damage_class: str | None = None
    npc_class: str | None = None
    auto_created: bool = False  # stamped by the mook hook; gates the prune (B2)


# B2 — every engine field sits in exactly one set (exhaustiveness enforced by
# test); `update_npc` writes only MUTABLE_FIELDS, `traits` keys included.
#
# The statblock is IMMUTABLE here in the sense this partition actually carries:
# not writable by `update_npc`, the LLM's tool. The engine mutates hp constantly
# through its own damage path, which never consults this partition — letting the
# LLM name a field that takes an integer is exactly the leak ADR 0003 closes.
MUTABLE_FIELDS: frozenset[str] = frozenset({"name", "condition", "location", "faction", "traits"})
IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "slug",
        "lifecycle",
        "psychology",
        "met_player",
        "last_interactions",
        "hp",
        "max_hp",
        "defense",
        "attack_mod",
        "damage_class",
        "npc_class",
        "auto_created",
    }
)
