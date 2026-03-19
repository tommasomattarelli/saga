"""World state integrity checker for playtests."""


def check_world_consistency(world_state: dict) -> list[str]:
    """Check world state for logical inconsistencies.

    Returns a list of warnings/errors found.
    """
    issues = []

    # Check time validity
    time_data = world_state.get("time", {})
    hour = time_data.get("hour", 0)
    if not (0 <= hour < 24):
        issues.append(f"Invalid hour: {hour}")

    # Check companion HP
    companions = world_state.get("companions", {})
    for name, data in companions.items():
        if isinstance(data, dict):
            hp = data.get("hp", 0)
            max_hp = data.get("max_hp", 1)
            if hp > max_hp:
                issues.append(f"{name} HP ({hp}) exceeds max HP ({max_hp})")
            if hp < 0:
                issues.append(f"{name} has negative HP ({hp})")

    return issues
