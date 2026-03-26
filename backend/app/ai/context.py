"""Context assembler - builds the prompt with budget management."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import get_gameplay_config
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
    max_history_turns: int | None = None,
) -> GameContext:
    """Build the full context for a DM AI call.

    Uses the configurable Active Window size for verbatim turns,
    and loads compressed summaries for older turns.
    """
    from app.ai.prompts.dm import build_dm_system_prompt

    config = get_gameplay_config()
    window_size = max_history_turns if max_history_turns is not None else config.context_window_turns

    # Load verbatim turns for the Active Window
    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign.id)
        .order_by(Turn.turn_number.desc())
        .limit(window_size)
    )
    recent_turns = list(reversed(result.scalars().all()))

    messages = []
    for turn in recent_turns:
        messages.append({"role": "user", "content": turn.player_action})
        messages.append({"role": "assistant", "content": turn.narration})

    messages.append({"role": "user", "content": player_action})

    importance = score_importance(player_action, campaign)

    # Load compressed summaries for turns before the window
    summary_context = ""
    if recent_turns:
        oldest_in_window = recent_turns[0].turn_number
        if oldest_in_window > 1:
            summary_result = await db.execute(
                select(Turn.summary)
                .where(
                    Turn.campaign_id == campaign.id,
                    Turn.turn_number < oldest_in_window,
                    Turn.summary.isnot(None),
                )
                .order_by(Turn.turn_number.desc())
                .limit(5)
            )
            summaries = [s for (s,) in summary_result.all() if s]
            if summaries:
                # Deduplicate batch summaries (multiple turns may share the same batch summary)
                seen = set()
                unique = []
                for s in reversed(summaries):
                    if s not in seen:
                        seen.add(s)
                        unique.append(s)
                summary_context = "\n".join(unique)

    system_prompt = build_dm_system_prompt(campaign, summary_context=summary_context)

    return GameContext(
        system_prompt=system_prompt,
        messages=messages,
        importance_score=importance,
        active_quests=campaign.quests.get("active", []) if campaign.quests else [],
        recent_events=[t.summary or t.narration[:100] for t in recent_turns[-3:]],
    )


def score_importance(player_action: str, campaign: Campaign) -> int:
    """Score the importance of a scene (0-10) for model routing."""
    score = 5

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
