"""Background Fact Extractor — extracts atomic facts from each game turn."""

from __future__ import annotations

import json
import uuid

import structlog

from app.ai.embeddings import generate_embedding
from app.ai.providers.base import get_provider, logged_generate
from app.ai.router import AICallType, get_gameplay_config, route_ai_call
from app.ai.sanitizer import strip_code_fences
from app.models.memory_fact import MemoryFact

logger = structlog.get_logger()

_MAX_FACT_RAW_CHARS = 4000

FACT_EXTRACTION_PROMPT = """You are a fact extractor for a tabletop RPG game. Extract 1-5 atomic facts from this game turn.

Each fact should be a single, self-contained piece of information about a named entity.

Entity types: npc, location, quest, item, event, secret

Player action: {player_action}
DM narration: {narration}
{npc_section}

Output ONLY valid JSON:
{{"facts": [{{"entity_name": "ExactName", "entity_type": "npc|location|quest|item|event|secret", "content": "Atomic fact in natural language"}}]}}

Rules:
- Use the exact entity name as it appears in the text
- Each fact should be independently understandable
- Include the turn context (what happened, not just who exists)
- Prefer facts about relationships, state changes, and decisions
- If nothing notable happened, return {{"facts": []}}"""


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
        npc_section = "NPC dialogues:\n" + "\n".join(f"- {d}" for d in npc_dialogues)

    prompt_text = (
        FACT_EXTRACTION_PROMPT.replace("{player_action}", player_action)
        .replace("{narration}", narration)
        .replace("{npc_section}", npc_section)
    )

    # Use a minimal context for routing (importance 0 → budget model)
    from app.ai.context import GameContext

    dummy_context = GameContext(
        system_prompt="",
        messages=[],
        importance_score=0,
    )
    model_config = await route_ai_call(AICallType.MEMORY_COMPRESSION, dummy_context)
    provider = get_provider(model_config.provider)

    raw = await logged_generate(
        provider,
        caller="fact_extractor",
        system_prompt="You extract structured facts from RPG game turns.",
        messages=[{"role": "user", "content": prompt_text}],
        model=model_config.model,
        temperature=0.2,
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

        async with async_session() as db:
            for fact_data in facts:
                entity_name = str(fact_data.get("entity_name")).strip()
                entity_type = str(fact_data.get("entity_type") or "event").strip()
                content = str(fact_data.get("content")).strip()

                embedding = await generate_embedding(content)

                fact = MemoryFact(
                    campaign_id=campaign_id,
                    turn_number=turn_number,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    content=content,
                    embedding=embedding,
                )
                db.add(fact)

            await db.commit()
            logger.info(
                "facts_extracted",
                campaign_id=str(campaign_id),
                turn=turn_number,
                count=len(facts),
            )

    except Exception:
        logger.exception("fact_extraction_failed", campaign_id=str(campaign_id), turn=turn_number)
