"""Background Fact Extractor — extracts atomic facts from each game turn."""

from __future__ import annotations

import json
import uuid

import structlog

from app.ai.prompts.loader import template
from app.ai.providers.base import logged_generate
from app.ai.router import get_gameplay_config, get_generation
from app.ai.sanitizer import strip_code_fences
from app.models.memory_fact import MemoryFact

logger = structlog.get_logger()

_MAX_FACT_RAW_CHARS = 4000

FACT_EXTRACTION_PROMPT = template("fact_extractor", "base")


def _is_storable(fact: object) -> bool:
    """Model output is untrusted — a fact without a name or a body cannot be stored."""
    if not isinstance(fact, dict):
        return False
    return bool(str(fact.get("entity_name") or "").strip()) and bool(
        str(fact.get("content") or "").strip()
    )


async def extract_facts(
    player_action: str,
    narration: str,
    npc_dialogues: list[str] | None = None,
) -> list[dict]:
    """Extract atomic facts from one turn. Persistence-free so the eval derive pass
    can reuse the real extractor without a database."""
    npc_section = ""
    if npc_dialogues:
        npc_section = template("fact_extractor", "npc_section").format(
            dialogues="\n".join(f"- {d}" for d in npc_dialogues)
        )

    prompt_text = (
        FACT_EXTRACTION_PROMPT.replace("{player_action}", player_action)
        .replace("{narration}", narration)
        .replace("{npc_section}", npc_section)
    )

    provider, model_config = await get_generation()

    raw = await logged_generate(
        provider,
        caller="fact_extractor",
        system_prompt=template("fact_extractor", "system"),
        messages=[{"role": "user", "content": prompt_text}],
        model=model_config.model,
        max_tokens=model_config.max_tokens,
    )

    if len(raw) > _MAX_FACT_RAW_CHARS:
        logger.warning("fact_extraction_anomalous_output", raw_length=len(raw))
        return []

    cleaned = strip_code_fences(raw)
    if not cleaned.strip():
        return []

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        from json_repair import repair_json

        try:
            data = json.loads(repair_json(cleaned))
        except (json.JSONDecodeError, ValueError):
            logger.warning("fact_extraction_unparseable", raw_preview=cleaned[:200])
            return []

    facts = data if isinstance(data, list) else data.get("facts", [])
    if not isinstance(facts, list):
        logger.warning("fact_extraction_anomalous_output", raw_preview=cleaned[:200])
        return []

    # Filter before capping: a malformed entry must not consume one of the five slots.
    return [f for f in facts if _is_storable(f)][:5]


async def extract_and_store_facts(
    campaign_id: uuid.UUID,
    turn_number: int,
    player_action: str,
    narration: str,
    npc_dialogues: list[str] | None = None,
) -> None:
    """Fire-and-forget: extract atomic facts via budget model, store in memory_facts.

    Uses an independent DB session since this runs as a background task
    after the turn transaction has already committed.
    """
    config = get_gameplay_config()
    if not config.fact_extraction_enabled:
        return

    try:
        facts = await extract_facts(player_action, narration, npc_dialogues)
        if not facts:
            return

        from app.dependencies import async_session

        stored_facts = []
        for fact_data in facts:
            entity_name = str(fact_data.get("entity_name")).strip()
            entity_type = str(fact_data.get("entity_type") or "event").strip()
            content = str(fact_data.get("content")).strip()
            stored_facts.append(
                MemoryFact(
                    campaign_id=campaign_id,
                    turn_number=turn_number,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    content=content,
                )
            )
        async with async_session() as db:
            from sqlalchemy import text

            from app.memory.embedding_queue import enqueue_source_embedding
            from app.models.source_embedding import EmbeddingSourceType

            await db.execute(
                text("SELECT id FROM campaigns WHERE id = :cid FOR UPDATE"), {"cid": campaign_id}
            )
            db.add_all(stored_facts)
            await db.flush()
            for fact in stored_facts:
                await enqueue_source_embedding(
                    db,
                    campaign_id=campaign_id,
                    source_type=EmbeddingSourceType.MEMORY_FACT,
                    source_id=fact.id,
                    source_text=fact.content,
                )
            await db.commit()
            from app.memory.embedding_worker import wake_embedding_worker

            wake_embedding_worker()
            logger.info(
                "facts_extracted",
                campaign_id=str(campaign_id),
                turn=turn_number,
                count=len(facts),
            )

    except Exception:
        logger.exception("fact_extraction_failed", campaign_id=str(campaign_id), turn=turn_number)
