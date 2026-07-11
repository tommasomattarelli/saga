"""ADR 0009 — bundled default NPC descriptive fields + resolution (G2).

The default mirrors `worlds/the-awakening/taxonomy.yaml` (the copyable source
for new worlds) and is the fallback for taxonomies predating the block.
`dreads` deliberately avoids the name of the `fear` psychology axis.
"""

from app.models.npc_fields import NpcFieldDef


def _field(name: str, default: str = "", scene: bool = False) -> NpcFieldDef:
    return NpcFieldDef(name=name, default=default, scene=scene)


DEFAULT_NPC_FIELDS: list[NpcFieldDef] = [
    _field("role", "Commoner", scene=True),
    _field("appearance", scene=True),
    _field("personality"),
    _field("motivation"),
    _field("background"),
    _field("ideal"),
    _field("bond"),
    _field("flaw"),
    _field("mannerisms"),
    _field("secret"),
    _field("dreads"),
]


def resolve_npc_fields(taxonomy: dict | None) -> list[NpcFieldDef]:
    block = (taxonomy or {}).get("npc_fields")
    return [NpcFieldDef(**f) for f in block] if block else DEFAULT_NPC_FIELDS


def default_traits(fields: list[NpcFieldDef]) -> dict[str, str]:
    return {f.name: f.default for f in fields}
