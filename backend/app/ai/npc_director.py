"""NPC Actor-Director — parallel LLM calls for independent NPC dialogue."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from functools import partial

import structlog

from app.ai.generation_context import generation_context
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import execute_generation
from app.ai.generation_execution_ledger import InMemoryGenerationLedger
from app.ai.npc_generation import build_npc_generation_request, validate_npc_response
from app.ai.npc_outcomes import (
    NPCFailure,
    NPCInteraction,
    NPCResult,
    actor_result_from_response,
)
from app.ai.prompts.npc import build_npc_prompt, build_npc_system_prompt
from app.ai.providers.usage import usage_scope
from app.ai.router import get_gameplay_config, get_generation, get_generation_recovery_policy
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
    npc_id: str | None = None
    step: int | None = None
    beat: int | None = None


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
        max_lines = get_gameplay_config().npc_max_lines
        request = build_npc_generation_request(
            system_prompt=build_npc_system_prompt(psychology, language),
            prompt=prompt,
            config=model_config,
            logical_result_id=uuid.uuid4().hex,
            psychology=psychology,
        )
        with usage_scope(role="actor", npc_name=npc_name):
            result = await execute_generation(
                request,
                provider,
                InMemoryGenerationLedger(),
                get_generation_recovery_policy(),
                Adapter(model_config.provider),
                validator=partial(
                    validate_npc_response,
                    max_lines=max_lines,
                    psychology=psychology,
                ),
            )

        return actor_result_from_response(npc_name, result.value)

    except Exception:
        logger.warning("npc_invoke_failed")
        return NPCFailure(npc_name)


async def _invoke_actor(actor: NPCInput) -> NPCResult:
    with usage_scope(
        role="actor",
        step=actor.step,
        beat=actor.beat,
        npc_id=actor.npc_id,
        npc_name=actor.npc_name,
    ):
        return await invoke_single_npc(
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


async def invoke_npcs_parallel(
    actors: list[NPCInput],
    user_id: uuid.UUID,
) -> list[NPCResult]:
    if not actors:
        return []
    tasks = [_invoke_actor(actor) for actor in actors]
    with generation_context(user_id):
        results = await asyncio.gather(*tasks, return_exceptions=True)

    dialogues = []
    for actor, r in zip(actors, results, strict=True):
        if isinstance(r, NPCInteraction | NPCFailure):
            dialogues.append(r)
        else:
            dialogues.append(NPCFailure(actor.npc_name))

    logger.info("npcs_invoked", count=len(dialogues))
    return dialogues
