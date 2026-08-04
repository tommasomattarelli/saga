"""ADR 0009 D1/D2 — the single NPC creation scaffold.

Every creation path (invoke_npc pre-hook, update_npc upsert, the ADR 0003 mook hook)
builds records here so they cannot drift: name + lifecycle=alive + psychology axis
defaults + a full statblock always present at birth. Detail levels (D2): minimal =
engine contract only; standard and rich = traits seeded from the world's npc_fields
defaults (rich additionally gets fill-in-character prompt guidance — an S3 surface,
not a schema difference).
"""

from app.core.npc_classes import DEFAULT_NPC_CLASSES, draw_statblock, statblock_defaults
from app.core.npc_fields import DEFAULT_NPC_FIELDS, default_traits
from app.core.psychology import DEFAULT_PSYCHOLOGY, default_values
from app.models.npc import NpcEngineRecord
from app.models.npc_class import NpcClassDef
from app.models.npc_fields import NpcFieldDef
from app.models.psychology import PsychologyDef


def create_npc_record(
    name: str,
    detail: str = "standard",
    psychology: PsychologyDef | None = None,
    npc_fields: list[NpcFieldDef] | None = None,
    npc_class: str | None = None,
    npc_classes: list[NpcClassDef] | None = None,
    location: str | None = None,
    auto_created: bool = False,
    statblock: dict | None = None,
) -> dict:
    fields = npc_fields or DEFAULT_NPC_FIELDS
    block = draw_statblock(
        npc_class or statblock_defaults()["npc_class"],
        npc_classes or DEFAULT_NPC_CLASSES,
        authored=statblock,
    )
    return NpcEngineRecord(
        name=name,
        psychology=default_values(psychology or DEFAULT_PSYCHOLOGY),
        traits={} if detail == "minimal" else default_traits(fields),
        location=location,
        auto_created=auto_created,
        **block,
    ).model_dump()
