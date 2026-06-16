"""NPC Actor-Director — parallel LLM calls for independent NPC dialogue."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import structlog

from app.ai.prompts.npc import build_npc_prompt
from app.ai.providers.base import get_provider, logged_generate
from app.ai.router import AICallType, get_gameplay_config, route_ai_call
from app.ai.sanitizer import strip_code_fences
from app.models.campaign import Campaign

logger = structlog.get_logger()


@dataclass
class NPCDialogue:
    npc_name: str
    dialogue: str
    action: str | None = None
    disposition_change: int = 0
    reveals_secret: bool = False


async def invoke_single_npc(
    npc_name: str,
    npc_profile: dict,
    player_action: str,
    dm_narration: str,
) -> NPCDialogue:
    """Call a budget LLM for a single NPC's response."""
    from app.ai.context import GameContext

    prompt = build_npc_prompt(npc_profile, player_action=player_action, dm_narration=dm_narration)

    dummy_context = GameContext(
        system_prompt="",
        messages=[],
        importance_score=0,
        active_quests=[],
        recent_events=[],
    )
    model_config = await route_ai_call(AICallType.NPC_BEHAVIOR, dummy_context)
    provider = get_provider(model_config.provider)

    try:
        raw = await logged_generate(
            provider,
            caller=f"npc_director:{npc_name}",
            system_prompt=f"You are {npc_name}, an NPC in a tabletop RPG.",
            messages=[{"role": "user", "content": prompt}],
            model=model_config.model,
            temperature=model_config.temperature,
            max_tokens=300,
            json_mode=True,
        )

        cleaned = strip_code_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            from json_repair import repair_json

            data = json.loads(repair_json(cleaned))

        return NPCDialogue(
            npc_name=npc_name,
            dialogue=data.get("dialogue", "..."),
            action=data.get("action"),
            disposition_change=int(data.get("disposition_change", 0)),
            reveals_secret=bool(data.get("reveals_secret", False)),
        )

    except Exception:
        logger.warning("npc_invoke_failed", npc_name=npc_name, exc_info=True)
        return NPCDialogue(npc_name=npc_name, dialogue="...")


async def invoke_npcs_parallel(
    npc_names: list[str],
    campaign: Campaign,
    player_action: str,
    dm_narration: str,
) -> list[NPCDialogue]:
    """Invoke NPC dialogue calls in parallel, respecting the configured cap."""
    config = get_gameplay_config()
    max_npcs = config.max_npc_calls

    if max_npcs <= 0 or not npc_names:
        return []

    names = npc_names[:max_npcs]
    npcs_data = campaign.world_state.get("npcs", {}) if campaign.world_state else {}

    tasks = []
    for name in names:
        # Look up NPC profile from world_state, or create a minimal one
        profile = npcs_data.get(name, {"name": name})
        if "name" not in profile:
            profile["name"] = name

        tasks.append(
            invoke_single_npc(
                npc_name=name,
                npc_profile=profile,
                player_action=player_action,
                dm_narration=dm_narration,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    dialogues = []
    for r in results:
        if isinstance(r, NPCDialogue):
            dialogues.append(r)
        else:
            logger.warning("npc_gather_exception", error=str(r))

    logger.info("npcs_invoked", count=len(dialogues), names=[d.npc_name for d in dialogues])
    return dialogues
