"""Death system — the only thing campaign difficulty governs (ADR 0003 B8).

Rolls and damage are identical at every difficulty; hardness comes from the fiction.
An unrecognised difficulty falls through to `hard`, never to `easy`: a lookup miss
must not silently make the player immortal.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config_loader import load_saga_config


@dataclass
class DeathCheckResult:
    """Result of a player death check."""

    is_dead: bool
    difficulty: str
    action: str  # "alive" | "near_death" | "fate_intervention" | "dead"
    narrative_instruction: str
    fate_interventions_remaining: int | None = None


def _fate_interventions() -> int:
    return int(load_saga_config()["campaign_difficulty"]["fate_interventions"])


def check_player_death(
    character_data: dict,
    difficulty: str,
    world_state: dict,
) -> DeathCheckResult:
    """Check whether the player's HP has reached 0, and what that means here."""
    hp = character_data.get("hp", {})
    current_hp = hp.get("current", 1)

    if current_hp > 0:
        return DeathCheckResult(
            is_dead=False,
            difficulty=difficulty,
            action="alive",
            narrative_instruction="",
        )

    if difficulty == "easy":
        hp["current"] = 1
        character_data["hp"] = hp
        return DeathCheckResult(
            is_dead=False,
            difficulty=difficulty,
            action="near_death",
            narrative_instruction=(
                "The player would have died, but this campaign never kills them. "
                "Narrate a dramatic near-death moment — a miraculous dodge, "
                "an ally's last-second intervention, or sheer luck. "
                "Then describe consequences: capture, forced retreat, equipment loss, "
                "or reputation damage. Never actual death."
            ),
        )

    if difficulty == "medium":
        total = _fate_interventions()
        lives = world_state.get("fate_interventions_left", total)
        if lives > 0:
            used = total - lives + 1
            costs = {
                1: "Minor cost: lose an item, gain a scar, or owe a debt.",
                2: (
                    "Major cost: lose a memory, a companion is endangered, "
                    "or a permanent stat reduction."
                ),
                3: (
                    "Severe cost: lose a companion, a dark power claims a piece of the "
                    "player's soul, or the world changes irreversibly."
                ),
            }
            return DeathCheckResult(
                is_dead=False,
                difficulty=difficulty,
                action="fate_intervention",
                narrative_instruction=(
                    f"The player died but fate intervenes (intervention #{used}, "
                    f"{lives - 1} remaining). Narrate a miraculous survival. "
                    f"{costs.get(used, 'Severe cost.')} "
                    "The survival must feel earned and costly, not cheap."
                ),
                fate_interventions_remaining=lives - 1,
            )
        return DeathCheckResult(
            is_dead=True,
            difficulty=difficulty,
            action="dead",
            narrative_instruction=(
                "Every fate intervention is spent. The player dies permanently. "
                "Narrate a memorable, dignified end to their story — an epilogue "
                "that honours what they accomplished."
            ),
        )

    return DeathCheckResult(
        is_dead=True,
        difficulty=difficulty,
        action="dead",
        narrative_instruction=(
            "The player has fallen and death is final here. "
            "Narrate a memorable death scene and a brief epilogue "
            "summarizing what they achieved in their journey."
        ),
    )
