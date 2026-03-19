"""Tiered memory compression for turn history."""

import structlog

logger = structlog.get_logger()

# Compression tiers:
# Tier 0 (recent): Full turn data (last 10 turns)
# Tier 1 (medium): Summary only (turns 11-50)
# Tier 2 (old): Embedded vectors only (turns 50+)


async def compress_turn_to_summary(narration: str, player_action: str) -> str:
    """Compress a full turn into a brief summary.

    For now uses a simple heuristic. Will be replaced with AI summarization.
    """
    # Take first sentence of narration + player action summary
    first_sentence = narration.split(".")[0] + "." if "." in narration else narration[:200]
    action_brief = player_action[:100]
    return f"Player: {action_brief} | DM: {first_sentence}"


def should_compress(turn_number: int, current_turn: int) -> int:
    """Determine compression tier for a turn.

    Returns:
        0: full data
        1: summary only
        2: embedding only
    """
    age = current_turn - turn_number
    if age <= 10:
        return 0
    elif age <= 50:
        return 1
    else:
        return 2
