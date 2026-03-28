"""Death system — handles player death based on campaign death mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeathCheckResult:
    """Result of a player death check."""

    is_dead: bool
    death_mode: str
    action: str  # "alive" | "near_death" | "fate_intervention" | "dead"
    narrative_instruction: str
    destino_lives_remaining: int | None = None


def check_player_death(
    character_data: dict,
    death_mode: str,
    world_state: dict,
) -> DeathCheckResult:
    """Check if the player's HP has reached 0 and determine outcome.

    Returns a DeathCheckResult with instructions for the engine and DM.
    """
    hp = character_data.get("hp", {})
    current_hp = hp.get("current", 1)

    if current_hp > 0:
        return DeathCheckResult(
            is_dead=False,
            death_mode=death_mode,
            action="alive",
            narrative_instruction="",
        )

    if death_mode == "cronista":
        hp["current"] = 1
        character_data["hp"] = hp
        return DeathCheckResult(
            is_dead=False,
            death_mode=death_mode,
            action="near_death",
            narrative_instruction=(
                "The player would have died but is in Cronista mode. "
                "Narrate a dramatic near-death moment — a miraculous dodge, "
                "an ally's last-second intervention, or divine luck. "
                "Then describe consequences: capture, forced retreat, equipment loss, "
                "or reputation damage. Never actual death."
            ),
        )

    if death_mode == "destino":
        lives = world_state.get("destino_lives", 3)
        if lives > 0:
            intervention_number = 4 - lives
            costs = {
                1: "Minor cost: lose an item, gain a scar, or owe a debt.",
                2: "Major cost: lose a memory, a companion is endangered, or a permanent stat reduction.",
                3: "Severe cost: lose a companion, a dark power claims a piece of the player's soul, or the world changes irreversibly.",
            }
            cost_hint = costs.get(intervention_number, "Severe cost.")
            return DeathCheckResult(
                is_dead=False,
                death_mode=death_mode,
                action="fate_intervention",
                narrative_instruction=(
                    f"The player died but Fate intervenes (intervention #{intervention_number}, "
                    f"{lives - 1} remaining). Narrate a miraculous survival. {cost_hint} "
                    "The survival must feel earned and costly, not cheap."
                ),
                destino_lives_remaining=lives - 1,
            )
        return DeathCheckResult(
            is_dead=True,
            death_mode=death_mode,
            action="dead",
            narrative_instruction=(
                "All fate interventions are spent. The player dies permanently. "
                "Narrate a memorable, dignified end to their story — an epilogue "
                "that honors what they accomplished."
            ),
        )

    # Ironman — permanent death
    return DeathCheckResult(
        is_dead=True,
        death_mode=death_mode,
        action="dead",
        narrative_instruction=(
            "The player has fallen in Ironman mode. Death is final. "
            "Narrate a memorable death scene and a brief epilogue "
            "summarizing what they achieved in their journey."
        ),
    )
