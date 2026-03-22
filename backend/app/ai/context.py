"""Context assembler - builds the prompt with budget management."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.turn import Turn


@dataclass
class GameContext:
    """Assembled context for an AI call."""

    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)
    importance_score: int = 5
    active_quests: list[dict] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)


async def build_context(
    campaign: Campaign,
    player_action: str,
    db: AsyncSession,
    max_history_turns: int = 10,
) -> GameContext:
    """Build the full context for a DM AI call."""
    from app.ai.prompts.dm import build_dm_system_prompt


    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign.id)
        .order_by(Turn.turn_number.desc())
        .limit(max_history_turns)
    )
    recent_turns = list(reversed(result.scalars().all()))


    messages = []
    for turn in recent_turns:
        messages.append({"role": "user", "content": turn.player_action})
        messages.append({"role": "assistant", "content": turn.narration})


    messages.append({"role": "user", "content": player_action})


    importance = score_importance(player_action, campaign)


    system_prompt = build_dm_system_prompt(campaign)

    return GameContext(
        system_prompt=system_prompt,
        messages=messages,
        importance_score=importance,
        active_quests=campaign.quests.get("active", []) if campaign.quests else [],
        recent_events=[t.summary or t.narration[:100] for t in recent_turns[-3:]],
    )


def score_importance(player_action: str, campaign: Campaign) -> int:
    """Score the importance of a scene (0-10) for model routing."""
    score = 5  # Default: medium importance

    action_lower = player_action.lower()


    high_keywords = ["attack", "fight", "confront", "betray", "confess", "reveal", "final"]
    if any(kw in action_lower for kw in high_keywords):
        score += 2


    low_keywords = ["look around", "rest", "wait", "inventory", "check"]
    if any(kw in action_lower for kw in low_keywords):
        score -= 2


    if campaign.world_state.get("in_combat"):
        score += 2

    return max(0, min(10, score))
