"""Rolling story summary — anchored iterative summarization via budget LLM.

Updated every N turns (see gameplay.global_summary_update_every).
Extends the previous summary with the last batch rather than regenerating.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.loader import template
from app.ai.router import get_gameplay_config, get_generation
from app.memory.compressor import summary_from
from app.models.campaign import Campaign
from app.models.turn import Turn

logger = structlog.get_logger()

INITIAL_PROMPT = template("global_summary", "initial")
UPDATE_PROMPT = template("global_summary", "update")


def _format_turns(turns: list[Turn]) -> str:
    return "\n".join(
        f"Turn {t.turn_number}: Player: {(t.player_action or '')[:200]} → DM: {(t.narration or '')[:300]}"
        for t in turns
    )


async def _generate_summary(prompt: str) -> str | None:
    from app.ai.providers.base import logged_generate

    provider, model_config = await get_generation()

    try:
        raw = await logged_generate(
            provider,
            caller="global_summary",
            system_prompt=template("global_summary", "system"),
            messages=[{"role": "user", "content": prompt}],
            model=model_config.model,
            max_tokens=model_config.max_tokens,
            json_mode=True,
        )
        return summary_from(raw)
    except Exception:
        logger.exception("global_summary_generation_failed")
        return None


async def update_global_summary(
    campaign_id: uuid.UUID | str,
    current_turn: int,
    db: AsyncSession,
) -> str | None:
    """Extend or generate the campaign's global_summary based on the most recent batch.

    Triggered every N turns (gameplay.global_summary_update_every).
    No-op if feature disabled or no new turns to summarize.
    Returns the new summary string, or None if generation failed / skipped.
    """
    config = get_gameplay_config()
    if not config.global_summary_enabled:
        return None

    batch_size = max(1, config.global_summary_update_every)

    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        return None

    lower = max(1, current_turn - batch_size + 1)
    batch_result = await db.execute(
        select(Turn)
        .where(
            Turn.campaign_id == campaign_id,
            Turn.turn_number >= lower,
            Turn.turn_number <= current_turn,
        )
        .order_by(Turn.turn_number.asc())
    )
    batch = list(batch_result.scalars().all())
    await db.close()
    if not batch:
        return None

    turns_text = _format_turns(batch)
    existing = (campaign.global_summary or "").strip()
    if len(existing) > config.global_summary_max_input_chars:
        existing = existing[-config.global_summary_max_input_chars :]

    if existing:
        prompt = UPDATE_PROMPT.format(existing=existing, turns_text=turns_text)
    else:
        prompt = INITIAL_PROMPT.format(turns_text=turns_text)

    summary = await _generate_summary(prompt)
    if not summary:
        return None

    campaign.global_summary = summary
    await db.execute(
        update(Campaign).where(Campaign.id == campaign_id).values(global_summary=summary)
    )
    await db.flush()
    logger.info(
        "global_summary_updated",
        campaign_id=str(campaign_id),
        current_turn=current_turn,
        length=len(summary),
    )
    return summary
