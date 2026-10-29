"""NPC Actor-Director — parallel LLM calls for independent NPC dialogue."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass

import structlog

from app.ai.generation_context import generation_context
from app.ai.npc_outcomes import NPCFailure, NPCInteraction, NPCResult, parse_actor_result
from app.ai.prompts.loader import template
from app.ai.prompts.npc import build_npc_prompt
from app.ai.providers.base import logged_generate
from app.ai.router import get_gameplay_config, get_generation
from app.ai.sanitizer import strip_code_fences
from app.models.psychology import PsychologyDef

logger = structlog.get_logger()


@dataclass(frozen=True)
class NPCInput:
    npc_name: str
    npc_profile: dict
    player_action: str
    invocation_context: str = ""
    dm_narration: str = ""
    observed_beats: str = ""
    scene_context: str = ""
    psychology: PsychologyDef | None = None
    fill_empty_traits: bool = False
    language: str = "en"


async def invoke_single_npc(
    npc_name: str,
    npc_profile: dict,
    player_action: str,
    dm_narration: str,
    psychology: PsychologyDef | None = None,
    fill_empty_traits: bool = False,
    language: str = "en",
    invocation_context: str = "",
    observed_beats: str = "",
    scene_context: str = "",
) -> NPCResult:
    prompt = build_npc_prompt(
        npc_profile,
        player_action=player_action,
        dm_narration=dm_narration,
        psychology=psychology,
        fill_empty_traits=fill_empty_traits,
        language=language,
        invocation_context=invocation_context,
        observed_beats=observed_beats,
        scene_context=scene_context,
    )

    try:
        provider, model_config = await get_generation()
        raw = await logged_generate(
            provider,
            caller=f"npc_director:{npc_name}",
            system_prompt=template("npc", "system").format(name=npc_name),
            messages=[{"role": "user", "content": prompt}],
            model=model_config.model,
            max_tokens=model_config.max_tokens,
            json_mode=True,
        )

        cleaned = strip_code_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            from json_repair import repair_json

            data = json.loads(repair_json(cleaned))

        return parse_actor_result(npc_name, data, get_gameplay_config().npc_max_lines)

    except Exception:
        logger.warning("npc_invoke_failed", npc_name=npc_name, exc_info=True)
        return NPCFailure(npc_name)


async def invoke_npcs_parallel(
    actors: list[NPCInput],
    user_id: uuid.UUID,
) -> list[NPCResult]:
    if not actors:
        return []
    tasks = [
        invoke_single_npc(
            npc_name=actor.npc_name,
            npc_profile=actor.npc_profile,
            player_action=actor.player_action,
            invocation_context=actor.invocation_context,
            dm_narration=actor.dm_narration,
            observed_beats=actor.observed_beats,
            scene_context=actor.scene_context,
            psychology=actor.psychology,
            fill_empty_traits=actor.fill_empty_traits,
            language=actor.language,
        )
        for actor in actors
    ]
    with generation_context(user_id):
        results = await asyncio.gather(*tasks, return_exceptions=True)

    dialogues = []
    for actor, r in zip(actors, results, strict=True):
        if isinstance(r, NPCInteraction | NPCFailure):
            dialogues.append(r)
        else:
            dialogues.append(NPCFailure(actor.npc_name))

    logger.info("npcs_invoked", count=len(dialogues), names=[d.npc_name for d in dialogues])
    return dialogues
