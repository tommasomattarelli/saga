"""Off-screen world simulation - the world moves independently of the player."""

from dataclasses import dataclass


@dataclass
class WorldEvent:
    """An event that occurred in the world off-screen."""

    description: str
    faction: str | None = None
    location: str | None = None
    impact: str = "minor"  # minor, moderate, major


async def simulate_world_tick(
    world_state: dict,
    turn_number: int,
    player_location: str,
) -> list[WorldEvent]:
    """Simulate off-screen world events between turns.

    Called every N turns to advance faction politics, NPC movements,
    weather changes, and rumor propagation. Events near the player
    may be surfaced in the DM narration; distant events become rumors.
    """
    events: list[WorldEvent] = []

    # Advance time of day / weather
    time_data = world_state.get("time", {})
    hour = time_data.get("hour", 8)
    hour = (hour + 1) % 24
    world_state.setdefault("time", {})["hour"] = hour

    # Faction tick (every 5 turns)
    if turn_number % 5 == 0:
        factions = world_state.get("factions", {})
        for faction_name, faction_data in factions.items():
            # AI will generate specific faction events
            # This is the structured hook for it
            if faction_data.get("active_plan"):
                events.append(
                    WorldEvent(
                        description=f"{faction_name} advances their plans",
                        faction=faction_name,
                        impact="moderate",
                    )
                )

    return events
