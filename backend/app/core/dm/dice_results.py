from app.core.dice import DifficultyLevel, resolve_check
from app.core.dm.dm_helpers import get_or_create_segment
from app.core.health import HazardClass, draw_hazard_damage
from app.memory.updater import apply_typed_updates

_STAT_FULL_NAMES = {
    "STR": "strength",
    "DEX": "dexterity",
    "CON": "constitution",
    "INT": "intelligence",
    "WIS": "wisdom",
    "CHA": "charisma",
}


def _character_modifier(char_data: dict, stat: str) -> int:
    abilities = char_data.get("abilities", {})
    full = _STAT_FULL_NAMES.get(stat.upper(), stat.lower())
    stat_score = abilities.get(full, abilities.get(stat, abilities.get(stat.lower(), 10)))
    return (stat_score - 10) // 2


def _handle_dice(
    args: dict, char_data: dict, step: int, narration_segments: list[dict]
) -> tuple[str, dict, dict]:
    stat = args.get("stat", "DEX")
    check = args.get("check") or f"{stat} check"
    reason = args.get("reason", "")
    difficulty = DifficultyLevel(args.get("difficulty", DifficultyLevel.NORMAL))
    resolution = resolve_check(
        modifier=_character_modifier(char_data, stat),
        difficulty=difficulty,
        advantage=bool(args.get("advantage")),
        disadvantage=bool(args.get("disadvantage")),
    )
    roll_obj = resolution.roll
    check_label = check.replace("_", " ").title()
    roll_data = {
        check_label: {
            "expression": roll_obj.expression,
            "rolls": roll_obj.rolls,
            "modifier": resolution.modifier,
            "difficulty": difficulty.value,
            "difficulty_draw": resolution.difficulty_draw,
            "total": resolution.total,
            "success": resolution.success,
            "outcome": resolution.outcome.value,
            "is_critical": resolution.is_critical,
        }
    }
    hazard = args.get("hazard_class")
    damage = 0
    if hazard:
        hp = char_data.get("hp", {})
        damage = draw_hazard_damage(
            HazardClass(hazard), resolution.outcome, int(hp.get("max", 10))
        )
        if damage:
            _, char_data = apply_typed_updates(
                {}, char_data, [{"key": "hp_change", "change": -damage}]
            )
        roll_data[check_label]["hazard_damage"] = damage
    seg = get_or_create_segment(narration_segments, step)
    seg["dice"] = {**(seg.get("dice") or {}), **roll_data}
    result_str = (
        f"{check.title()} check ({difficulty.value}): rolled {resolution.total} "
        f"({resolution.modifier:+d} modifier, {resolution.difficulty_draw:+d} difficulty) "
        f"→ {resolution.outcome.value}."
    )
    if hazard:
        current = char_data.get("hp", {}).get("current", 0)
        result_str += f" Hazard deals {damage} damage — HP now {current}."
    if reason:
        result_str += f" Context: {reason}"
    return result_str, roll_data, char_data
