"""Character service."""


def create_default_character(name: str, background: str = "adventurer") -> dict:
    """Create a default character data structure."""
    return {
        "name": name,
        "level": 1,
        "xp": 0,
        "hp": 20,
        "max_hp": 20,
        "ac": 10,
        "abilities": {
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        },
        "skills": {},
        "inventory": [],
        "gold": 10,
        "background": background,
        "notes": "",
    }
