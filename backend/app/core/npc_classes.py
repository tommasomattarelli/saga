"""ADR 0003 B3b — bundled default NPC classes + statblock drawing.

The default mirrors `worlds/the-awakening/taxonomy.yaml` (the copyable source for new
worlds) and is the fallback for taxonomies predating the block — the 0005/0009 pattern.
"""

import random

from app.config_loader import load_saga_config
from app.models.npc_class import NpcClassDef

DEFAULT_NPC_CLASSES: list[NpcClassDef] = [
    NpcClassDef(name="commoner", hp_class="weak", defense="easy", damage_class="unarmed"),
    NpcClassDef(name="royale", hp_class="weak", defense="easy", damage_class="light"),
    NpcClassDef(
        name="beast", hp_class="standard", defense="normal", damage_class="medium", attack_mod=2
    ),
    NpcClassDef(
        name="guard", hp_class="standard", defense="normal", damage_class="medium", attack_mod=2
    ),
    NpcClassDef(
        name="soldier", hp_class="standard", defense="hard", damage_class="medium", attack_mod=3
    ),
    NpcClassDef(
        name="commander", hp_class="tough", defense="hard", damage_class="heavy", attack_mod=5
    ),
]


def resolve_npc_classes(taxonomy: dict | None) -> list[NpcClassDef]:
    block = (taxonomy or {}).get("npc_classes")
    return [NpcClassDef(**c) for c in block] if block else DEFAULT_NPC_CLASSES


def statblock_defaults() -> dict:
    return load_saga_config()["combat"]["statblock_defaults"]


def _draw_hp(hp_class: str) -> int:
    low, high = load_saga_config()["combat"]["hp_classes"][hp_class]
    return random.randint(min(low, high), max(low, high))


def draw_statblock(
    npc_class: str,
    classes: list[NpcClassDef],
    authored: dict | None = None,
) -> dict:
    """Class template → concrete numbers. Authored values win; the rest is drawn."""
    defaults = statblock_defaults()
    template = next((c for c in classes if c.name == npc_class), None)
    if template is None:
        template = next((c for c in classes if c.name == defaults["npc_class"]), None)
    authored = authored or {}

    if template is None:
        block = {
            "npc_class": defaults["npc_class"],
            "defense": defaults["defense"],
            "damage_class": defaults["damage_class"],
            "attack_mod": defaults["attack_mod"],
        }
        hp_class = defaults["hp_class"]
    else:
        block = {
            "npc_class": template.name,
            "defense": template.defense.value,
            "damage_class": template.damage_class.value,
            "attack_mod": template.attack_mod,
        }
        hp_class = template.hp_class.value

    block.update({k: v for k, v in authored.items() if k in block})
    max_hp = int(authored.get("max_hp") or _draw_hp(authored.get("hp_class") or hp_class))
    return {**block, "hp": int(authored.get("hp") or max_hp), "max_hp": max_hp}
