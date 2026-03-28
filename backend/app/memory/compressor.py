"""Tiered memory compression for turn history."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import AICallType, get_gameplay_config, route_ai_call
from app.models.turn import Turn

logger = structlog.get_logger()

COMPRESSION_PROMPT = """Summarize this batch of RPG game turns in 2-3 sentences.
Focus on: key player decisions, consequences, NPC interactions, world changes.
Do NOT include meta-commentary — write as a narrative summary.

Turns:
{turns_text}

Summary:"""


async def compress_turn_to_summary(narration: str, player_action: str) -> str:
    """Compress a full turn into a brief summary (heuristic fallback)."""
    first_sentence = narration.split(".")[0] + "." if "." in narration else narration[:200]
    action_brief = player_action[:100]
    return f"Player: {action_brief} | DM: {first_sentence}"


async def compress_turns_batch_llm(turns: list[Turn]) -> str | None:
    """Compress a batch of turns into a 2-3 sentence summary via budget LLM."""
    from app.ai.context import GameContext
    from app.ai.providers.base import get_provider

    turns_text = "\n".join(
        f"Turn {t.turn_number}: Player: {t.player_action[:200]} → DM: {(t.narration or '')[:300]}"
        for t in turns
    )

    dummy_context = GameContext(
        system_prompt="",
        messages=[],
        importance_score=0,
        active_quests=[],
        recent_events=[],
    )
    model_config = await route_ai_call(AICallType.MEMORY_COMPRESSION, dummy_context)
    provider = get_provider(model_config.provider)

    try:
        raw = await provider.generate(
            system_prompt="You are a concise narrative summarizer for an RPG game.",
            messages=[
                {"role": "user", "content": COMPRESSION_PROMPT.format(turns_text=turns_text)}
            ],
            model=model_config.model,
            temperature=0.3,
            max_tokens=300,
        )
        return raw.strip()
    except Exception:
        logger.exception("llm_compression_failed")
        return None


async def ensure_compression(
    campaign_id: str,
    current_turn: int,
    db: AsyncSession,
) -> None:
    """Compress old turns beyond the Active Window that lack summaries.

    Processes in batches of 5 turns. Uses LLM if enabled, else heuristic.
    """
    config = get_gameplay_config()
    window_size = config.context_window_turns
    cutoff = current_turn - window_size

    if cutoff <= 0:
        return

    # Find turns beyond the window without summaries
    result = await db.execute(
        select(Turn)
        .where(
            Turn.campaign_id == campaign_id,
            Turn.turn_number <= cutoff,
            Turn.summary.is_(None),
        )
        .order_by(Turn.turn_number.asc())
        .limit(10)
    )
    uncompressed = list(result.scalars().all())

    if not uncompressed:
        return

    # Process in batches of 5
    batch_size = 5
    for i in range(0, len(uncompressed), batch_size):
        batch = uncompressed[i : i + batch_size]

        if config.compression_enabled:
            summary = await compress_turns_batch_llm(batch)
        else:
            summary = None

        for turn in batch:
            if summary:
                turn.summary = summary
            else:
                turn.summary = await compress_turn_to_summary(
                    turn.narration or "", turn.player_action or ""
                )

    await db.flush()
    logger.info("turns_compressed", campaign_id=campaign_id, count=len(uncompressed))


def should_compress(turn_number: int, current_turn: int) -> int:
    """Determine compression tier for a turn.

    Returns:
        0: full data (active window)
        1: summary only
        2: embedding only
    """
    config = get_gameplay_config()
    age = current_turn - turn_number
    if age <= config.context_window_turns:
        return 0
    elif age <= 50:
        return 1
    else:
        return 2
