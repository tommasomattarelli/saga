"""Tiered memory compression for turn history."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import (
    AICallType,
    get_gameplay_config,
    get_summarization_config,
    route_ai_call,
)
from app.ai.sanitizer import parse_json_payload
from app.models.turn import Turn

logger = structlog.get_logger()

COMPRESSION_PROMPT = """Summarize this batch of RPG game turns in 2-3 sentences of flowing prose.
Focus on: key player decisions, consequences, NPC interactions, world changes.
Do NOT include meta-commentary — write as a narrative summary.
Do NOT include verbatim NPC dialogue or quoted speech — paraphrase what was said and its effect.

Turns:
{turns_text}

Output ONLY valid JSON:
{{"summary": "the summary prose"}}"""


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    if "." in text:
        return text.split(".", 1)[0].strip() + "."
    return text[:200].strip()


def _prosa_verb(action: str) -> str:
    """Extract a short verb-phrase fragment from the player action."""
    action = (action or "").strip()
    if not action:
        return "acted"
    first_word = action.split()[0].lower()
    if first_word in {"i", "i'm", "im"}:
        rest = action.split(maxsplit=1)
        return rest[1][:100].strip() if len(rest) > 1 else action[:100]
    return action[:100]


async def compress_turn_to_summary(narration: str, player_action: str) -> str:
    """Compress a full turn into a brief prose summary (heuristic fallback)."""
    verb = _prosa_verb(player_action)
    scene = _first_sentence(narration)
    if scene:
        return f"The player {verb}. {scene}"
    return f"The player {verb}."


def summary_from(raw: str) -> str | None:
    """A summariser has no shape to fail, so reasoning prose would be stored as the
    answer. Requiring a JSON object gives it one (#78)."""
    data = parse_json_payload(raw)
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    logger.warning("summary_unreadable", raw_preview=raw[:200])
    return None


async def compress_turns_batch_llm(turns: list[Turn]) -> str | None:
    """Compress a batch of turns into a 2-3 sentence summary via budget LLM (single attempt)."""
    from app.ai.context import GameContext
    from app.ai.providers.base import get_provider, logged_generate

    turns_text = "\n".join(
        f"Turn {t.turn_number}: Player: {t.player_action[:200]} → DM: {(t.narration or '')[:300]}"
        for t in turns
    )

    dummy_context = GameContext(
        system_prompt="",
        messages=[],
        importance_score=0,
    )
    model_config = await route_ai_call(AICallType.MEMORY_COMPRESSION, dummy_context)
    provider = get_provider(model_config.provider)

    try:
        raw = await logged_generate(
            provider,
            caller="compressor",
            system_prompt="You are a concise narrative summarizer for an RPG game.",
            messages=[
                {"role": "user", "content": COMPRESSION_PROMPT.format(turns_text=turns_text)}
            ],
            model=model_config.model,
            temperature=0.3,
            max_tokens=model_config.max_tokens,
            json_mode=True,
        )
        return summary_from(raw)
    except Exception:
        logger.exception("llm_compression_failed")
        return None


async def compress_turns_batch_with_retry(turns: list[Turn]) -> str | None:
    """Compress a batch with exponential-backoff retries.

    Returns the summary string on success, or None if all retries fail.
    Retries on None results (LLM error) and on exceptions.
    """
    cfg = get_summarization_config()
    delays = cfg.retry_delays_seconds or [1, 5, 30]
    max_attempts = max(1, cfg.max_retries)

    for attempt in range(max_attempts):
        summary = await compress_turns_batch_llm(turns)
        if summary:
            return summary
        if attempt < max_attempts - 1:
            delay = delays[min(attempt, len(delays) - 1)]
            logger.warning(
                "summarization_retry",
                attempt=attempt + 1,
                max_attempts=max_attempts,
                delay=delay,
                batch_size=len(turns),
            )
            await asyncio.sleep(delay)

    logger.error("summarization_failed_after_retries", batch_size=len(turns))
    return None


def _batch_prefix(turns: list[Turn]) -> str:
    if not turns:
        return ""
    lo = min(t.turn_number for t in turns)
    hi = max(t.turn_number for t in turns)
    return f"[Turns {lo}-{hi}] " if lo != hi else f"[Turn {lo}] "


async def ensure_compression(
    campaign_id: str,
    current_turn: int,
    db: AsyncSession,
) -> None:
    """Compress old turns beyond the Active Window that lack summaries.

    Processes in batches of 5 turns with retry + idempotency.
    """
    config = get_gameplay_config()
    window_size = config.context_window_turns
    cutoff = current_turn - window_size

    if cutoff <= 0:
        return

    result = await db.execute(
        select(Turn)
        .where(
            Turn.campaign_id == campaign_id,
            Turn.turn_number <= cutoff,
            Turn.summary.is_(None),
            Turn.summarization_failed.is_(False),
        )
        .order_by(Turn.turn_number.asc())
        .limit(10)
    )
    uncompressed = list(result.scalars().all())

    if not uncompressed:
        return

    batch_size = 5
    for i in range(0, len(uncompressed), batch_size):
        batch = uncompressed[i : i + batch_size]

        if config.compression_enabled:
            summary = await compress_turns_batch_with_retry(batch)
        else:
            summary = None

        prefix = _batch_prefix(batch)
        llm_failed = config.compression_enabled and not summary
        for turn in batch:
            # Idempotency: skip if another task already wrote the summary
            if turn.summary is not None:
                continue
            if summary:
                turn.summary = f"{prefix}{summary}"
            else:
                # LLM disabled OR failed after retries → heuristic fallback
                turn.summary = await compress_turn_to_summary(
                    turn.narration or "", turn.player_action or ""
                )
                if llm_failed:
                    # Mark failed so subsequent cycles skip this turn (no infinite retry)
                    turn.summarization_failed = True

    await db.flush()
    logger.info("turns_compressed", campaign_id=campaign_id, count=len(uncompressed))
