"""Character service."""

CLASS_PRESETS: dict[str, dict[str, int]] = {
    "warrior": {
        "strength": 16,
        "constitution": 14,
        "dexterity": 12,
        "wisdom": 10,
        "intelligence": 8,
        "charisma": 10,
    },
    "rogue": {
        "dexterity": 16,
        "charisma": 14,
        "intelligence": 12,
        "constitution": 10,
        "strength": 10,
        "wisdom": 8,
    },
    "mage": {
        "intelligence": 16,
        "wisdom": 14,
        "charisma": 12,
        "dexterity": 10,
        "constitution": 8,
        "strength": 10,
    },
    "ranger": {
        "dexterity": 16,
        "wisdom": 14,
        "constitution": 12,
        "strength": 10,
        "intelligence": 10,
        "charisma": 8,
    },
    "cleric": {
        "wisdom": 16,
        "constitution": 14,
        "charisma": 12,
        "strength": 10,
        "dexterity": 10,
        "intelligence": 8,
    },
    "bard": {
        "charisma": 16,
        "dexterity": 14,
        "intelligence": 12,
        "wisdom": 10,
        "constitution": 10,
        "strength": 8,
    },
}

BASE_HP = 20


def create_default_character(
    name: str,
    archetype: str = "warrior",
    background: str = "adventurer",
) -> dict:
    """Create a character with class-based ability presets and nested HP."""
    abilities = CLASS_PRESETS.get(archetype, CLASS_PRESETS["warrior"]).copy()
    con_mod = (abilities["constitution"] - 10) // 2
    max_hp = BASE_HP + con_mod

    return {
        "name": name,
        "level": 1,
        "xp": 0,
        "hp": {"current": max_hp, "max": max_hp},
        "ac": 10,
        "abilities": abilities,
        "skills": {},
        "inventory": [],
        "gold": 10,
        "background": background,
        "archetype": archetype,
        "notes": "",
    }
