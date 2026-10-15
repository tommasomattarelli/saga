"""Context assembler - builds the prompt with budget management."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import get_gameplay_config
from app.memory.semantic import search_similar_facts
from app.models.campaign import Campaign
from app.models.turn import Turn

logger = structlog.get_logger()


@dataclass
class GameContext:
    """Assembled context for an AI call."""

    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)
    importance_score: int = 5


def _estimate_tokens(text: str) -> int:
    """Rough char-based token estimate (~4 chars/token)."""
    return len(text) // 4


def _enforce_token_budget(
    system_prompt: str,
    messages: list[dict],
    token_cap: int,
) -> list[dict]:
    """Drop the oldest verbatim turn pairs until total tokens fit under the cap.

    Preserves the last message (current player action) and keeps pairs (user+assistant) together.
    """
    total = _estimate_tokens(system_prompt) + sum(
        _estimate_tokens(m.get("content", "")) for m in messages
    )
    if total <= token_cap or len(messages) <= 1:
        return messages

    # Keep the trailing user message (current action) + pair everything else
    trailing = messages[-1]
    body = messages[:-1]

    while body and total > token_cap:
        dropped = body[:2] if len(body) >= 2 else body[:1]
        body = body[len(dropped) :]
        total -= sum(_estimate_tokens(m.get("content", "")) for m in dropped)

    logger.info(
        "context_token_budget_enforced",
        token_cap=token_cap,
        final_estimate=total,
        kept_pairs=len(body) // 2,
    )
    return body + [trailing]


async def _load_history(
    campaign: Campaign, player_action: str, db: AsyncSession, window_size: int
) -> tuple[list[dict], list[Turn]]:
    """Verbatim user/assistant pairs in the Active Window + the trailing action."""
    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign.id)
        .order_by(Turn.turn_number.desc())
        .limit(window_size)
    )
    recent_turns = list(reversed(result.scalars().all()))

    messages: list[dict] = []
    for turn in recent_turns:
        if not turn.narration:
            continue
        messages.append({"role": "user", "content": turn.player_action})
        messages.append({"role": "assistant", "content": turn.narration})
    messages.append({"role": "user", "content": player_action})
    return messages, recent_turns


async def _load_batch_summaries(
    campaign: Campaign, recent_turns: list[Turn], db: AsyncSession
) -> str:
    """Deduped summaries of turns older than the Active Window."""
    if not recent_turns:
        return ""
    oldest_in_window = recent_turns[0].turn_number
    if oldest_in_window <= 1:
        return ""

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
    seen: set[str] = set()
    unique: list[str] = []
    for s in reversed(summaries):
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return "\n".join(unique)


async def _recall_memories(
    campaign: Campaign,
    player_action: str,
    db: AsyncSession,
    query_embedding: list[float] | None,
) -> list[str]:
    """Top-K MemoryFacts relevant to the current action (pgvector recall)."""
    try:
        facts = await search_similar_facts(
            campaign_id=campaign.id,
            query=player_action,
            db=db,
            limit=3,
            query_embedding=query_embedding,
        )
        return [f.content for f in facts if f.content]
    except Exception:
        logger.exception("recalled_memories_lookup_failed", campaign_id=str(campaign.id))
        return []


async def build_context(
    campaign: Campaign,
    player_action: str,
    db: AsyncSession,
    max_history_turns: int | None = None,
    query_embedding: list[float] | None = None,
) -> GameContext:
    """Assemble the DM prompt from history, batch summaries, global summary, and recall.

    `query_embedding` (when provided) is reused for semantic recall so the
    embedding API call happens outside this DB session (rule 15).
    """
    from app.ai.prompts.dm import build_dm_system_prompt

    config = get_gameplay_config()
    window_size = (
        max_history_turns if max_history_turns is not None else config.context_window_turns
    )

    messages, recent_turns = await _load_history(campaign, player_action, db, window_size)
    summary_context = await _load_batch_summaries(campaign, recent_turns, db)
    recalled = await _recall_memories(campaign, player_action, db, query_embedding)
    global_summary = (campaign.global_summary or "").strip()

    system_prompt = build_dm_system_prompt(
        campaign,
        summary_context=summary_context,
        global_summary=global_summary,
        recalled_memories=recalled,
    )
    budgeted_messages = _enforce_token_budget(system_prompt, messages, config.context_token_cap)

    return GameContext(
        system_prompt=system_prompt,
        messages=budgeted_messages,
        importance_score=score_importance(player_action, campaign),
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

    return max(0, min(10, score))
