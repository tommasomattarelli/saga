"""Background Fact Extractor — extracts atomic facts from each game turn."""

from __future__ import annotations

import json
import uuid

import structlog

from app.ai.embeddings import generate_embedding
from app.ai.parser import _strip_fences
from app.ai.providers.base import get_provider, logged_generate
from app.ai.router import AICallType, get_gameplay_config, route_ai_call
from app.models.memory_fact import MemoryFact

logger = structlog.get_logger()

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

    npc_section = ""
    if npc_dialogues:
        npc_section = "NPC dialogues:\n" + "\n".join(f"- {d}" for d in npc_dialogues)

    prompt_text = FACT_EXTRACTION_PROMPT.format(
        player_action=player_action,
        narration=narration,
        npc_section=npc_section,
    )

    try:
        # Use a minimal context for routing (importance 0 → budget model)
        from app.ai.context import GameContext

        dummy_context = GameContext(
            system_prompt="",
            messages=[],
            importance_score=0,
            active_quests=[],
            recent_events=[],
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
            max_tokens=500,
        )

        # Parse the facts
        cleaned = _strip_fences(raw)
        if not cleaned.strip():
            return

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            from json_repair import repair_json

            try:
                data = json.loads(repair_json(cleaned))
            except (json.JSONDecodeError, ValueError):
                logger.warning("fact_extraction_unparseable", raw_preview=cleaned[:200])
                return

        facts = data if isinstance(data, list) else data.get("facts", [])
        if not facts:
            return

        # Store facts with embeddings
        from app.dependencies import async_session

        async with async_session() as db:
            for fact_data in facts[:5]:  # cap at 5
                entity_name = fact_data.get("entity_name", "").strip()
                entity_type = fact_data.get("entity_type", "event").strip()
                content = fact_data.get("content", "").strip()

                if not entity_name or not content:
                    continue

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
