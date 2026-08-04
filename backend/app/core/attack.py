"""ADR 0003 B4/B5 — one symmetric attack: a check with damage attached.

Any pair works (player→NPC, NPC→player, NPC→NPC), which is why the model where only
the player rolls lost: a mercenary ally swinging at a goblin is inexpressible there.
No LLM call happens here — an enemy's turn is engine arithmetic.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from app.ai.router import get_gameplay_config
from app.config_loader import load_saga_config
from app.core.dice import CheckResolution, DiceOutcome, DifficultyLevel, resolve_check, roll_dice
from app.core.health import PLAYER_TARGET, apply_hp_delta
from app.core.npc_classes import DEFAULT_NPC_CLASSES, resolve_npc_classes, statblock_defaults
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import npc_aliases, resolve_npc
from app.core.npc_scaffold import create_npc_record
from app.core.psychology import resolve_psychology
from app.models.npc_class import DamageClass


@dataclass
class AttackResult:
    world_state: dict
    char_data: dict
    error: str = ""
    attacker: str = ""
    target: str = ""
    attack_mod: int = 0
    difficulty: DifficultyLevel = DifficultyLevel.NORMAL
    outcome: DiceOutcome = DiceOutcome.HARD_FAILURE
    damage: int = 0
    target_hp: int = 0
    target_max_hp: int = 0
    target_died: bool = False
    resolution: CheckResolution | None = field(default=None)


def _combat_config() -> dict:
    return load_saga_config()["combat"]


def _player_modifier(char_data: dict, stat: str) -> int:
    abilities = char_data.get("abilities", {})
    full = {
        "STR": "strength",
        "DEX": "dexterity",
        "CON": "constitution",
        "INT": "intelligence",
        "WIS": "wisdom",
        "CHA": "charisma",
    }.get(stat.upper(), stat.lower())
    score = abilities.get(full, abilities.get(stat, abilities.get(stat.lower(), 10)))
    return (int(score) - 10) // 2


def _resolve_side(
    name: str,
    world_state: dict,
    char_data: dict,
    *,
    create_if_missing: bool,
    taxonomy: dict | None,
) -> tuple[str | None, str]:
    """Name → PLAYER_TARGET or an NPC uuid, via the 0009 F2 resolver (B4 typo guard)."""
    if name.strip().casefold() == str(char_data.get("name", "Player")).casefold():
        return PLAYER_TARGET, ""

    resolution = resolve_npc(name, world_state)
    if resolution.npc_id is not None:
        return resolution.npc_id, ""
    if resolution.candidates or not create_if_missing:
        return None, resolution.error or f"{name} is not here."
    # resolve_npc only reports an error for a name it knows (dead, removed, ambiguous);
    # anything it recognises is never silently re-created as a fresh mook.
    if resolution.error and not resolution.error.endswith("is not a known NPC."):
        return None, resolution.error

    # B4 typo guard — a near-miss is a misspelling, not a new combatant.
    near = difflib.get_close_matches(
        name, npc_aliases(world_state), n=3, cutoff=get_gameplay_config().npc_name_match_threshold
    )
    if near:
        return None, f"No one here is called '{name}'. Did you mean: {', '.join(near)}?"

    # B2 — a genuinely new name in a fight is a mook: a real record, minimal class,
    # planted at the current node so presence guards and the death writer work.
    return _create_mook(name, world_state, taxonomy), ""


def _create_mook(name: str, world_state: dict, taxonomy: dict | None) -> str:
    from uuid import uuid4

    record = create_npc_record(
        name,
        detail="minimal",
        psychology=resolve_psychology(taxonomy),
        npc_fields=resolve_npc_fields(taxonomy),
        npc_class=statblock_defaults()["npc_class"],
        npc_classes=resolve_npc_classes(taxonomy) or DEFAULT_NPC_CLASSES,
        location=world_state.get("meta", {}).get("current_location"),
        auto_created=True,
    )
    npc_id = str(uuid4())
    world_state.setdefault("npcs", {})[npc_id] = record
    return npc_id


def _statblock(target: str, world_state: dict) -> dict:
    if target == PLAYER_TARGET:
        return {}
    return world_state.get("npcs", {}).get(target, {})


def _defense_of(target: str, world_state: dict, char_data: dict) -> DifficultyLevel:
    config = _combat_config()
    if target == PLAYER_TARGET:
        level = _shift_for_dex(config["player_defense_default"], char_data)
    else:
        level = (
            _statblock(target, world_state).get("defense")
            or config["statblock_defaults"]["defense"]
        )
    return DifficultyLevel(level)


def _shift_for_dex(base: str, char_data: dict) -> str:
    """B3 — DEX nudges how hard the player is to hit, by at most one level."""
    ladder = list(DifficultyLevel)
    index = ladder.index(DifficultyLevel(base))
    shift = _combat_config()["defense_dex_shift"]
    dex = _player_modifier(char_data, "DEX")
    if dex >= int(shift["harder_at"]):
        index = min(index + 1, len(ladder) - 1)
    elif dex <= int(shift["easier_at"]):
        index = max(index - 1, 0)
    return ladder[index].value


def _damage_for(
    attacker: str,
    world_state: dict,
    char_data: dict,
    outcome: DiceOutcome,
    weapon_class: str | None,
) -> int:
    config = _combat_config()
    scale = float(config["tier_damage_scale"][outcome.value])
    if scale <= 0:
        return 0

    if attacker == PLAYER_TARGET:
        # No items until ADR 0010, so the LLM classifies the described weapon (B5).
        damage_class = weapon_class or config["statblock_defaults"]["damage_class"]
        stat = config["weapon_class_to_stat"][damage_class]
        attribute_mod = _player_modifier(char_data, stat)
    else:
        block = _statblock(attacker, world_state)
        damage_class = block.get("damage_class") or config["statblock_defaults"]["damage_class"]
        # NPCs have no attribute scores — attack_mod is their whole sheet (S0 note).
        attribute_mod = 0

    expression = config["damage_classes"][DamageClass(damage_class).value]
    dice_total = sum(
        roll_dice(expression).total for _ in range(2 if scale >= 2 else 1)
    )  # critical doubles the dice, not the modifier
    rolled = dice_total * (scale if scale < 2 else 1)
    return max(1, round(rolled) + attribute_mod)


def resolve_attack(
    world_state: dict,
    char_data: dict,
    attacker: str,
    target: str,
    weapon_class: str | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
    taxonomy: dict | None = None,
) -> AttackResult:
    """d20 + attack_mod(attacker) + draw(defense(target)) → tier → server damage."""
    base = AttackResult(
        world_state=world_state, char_data=char_data, attacker=attacker, target=target
    )

    attacker_id, error = _resolve_side(
        attacker, world_state, char_data, create_if_missing=False, taxonomy=taxonomy
    )
    if attacker_id is None:
        return AttackResult(**{**base.__dict__, "error": error})

    target_id, error = _resolve_side(
        target, world_state, char_data, create_if_missing=True, taxonomy=taxonomy
    )
    if target_id is None:
        return AttackResult(**{**base.__dict__, "error": error})

    if attacker_id == PLAYER_TARGET:
        stat = _combat_config()["weapon_class_to_stat"][
            weapon_class or _combat_config()["statblock_defaults"]["damage_class"]
        ]
        attack_mod = _player_modifier(char_data, stat)
    else:
        attack_mod = int(_statblock(attacker_id, world_state).get("attack_mod") or 0)

    defense = _defense_of(target_id, world_state, char_data)
    resolution = resolve_check(
        modifier=attack_mod, difficulty=defense, advantage=advantage, disadvantage=disadvantage
    )
    damage = _damage_for(attacker_id, world_state, char_data, resolution.outcome, weapon_class)

    world_state, char_data, hp, max_hp = apply_hp_delta(world_state, char_data, target_id, -damage)

    return AttackResult(
        world_state=world_state,
        char_data=char_data,
        attacker=attacker,
        target=target,
        attack_mod=attack_mod,
        difficulty=defense,
        outcome=resolution.outcome,
        damage=damage,
        target_hp=hp,
        target_max_hp=max_hp,
        target_died=hp == 0 and damage > 0,
        resolution=resolution,
    )
