"""NPC Actor-Director — parallel LLM calls for independent NPC dialogue."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.ai.generation_context import generation_context
from app.ai.prompts.loader import template
from app.ai.prompts.npc import build_npc_prompt
from app.ai.providers.base import logged_generate
from app.ai.router import get_gameplay_config, get_generation
from app.ai.sanitizer import strip_code_fences
from app.core.npc_resolver import resolve_npc
from app.core.psychology import resolve_psychology
from app.models.campaign import Campaign
from app.models.psychology import PsychologyDef

logger = structlog.get_logger()


@dataclass
class NPCDialogue:
    npc_name: str
    dialogue: str
    action: str | None = None
    axis_changes: dict[str, int] = field(default_factory=dict)
    reveals_secret: bool = False


def _parse_axis_changes(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(axis): int(delta)
        for axis, delta in raw.items()
        if isinstance(delta, int | float) and not isinstance(delta, bool)
    }


async def invoke_single_npc(
    npc_name: str,
    npc_profile: dict,
    player_action: str,
    dm_narration: str,
    psychology: PsychologyDef | None = None,
    fill_empty_traits: bool = False,
    generation: tuple[Any, Any] | None = None,
    language: str = "en",
) -> NPCDialogue:
    """Call a budget LLM for a single NPC's response.

    `generation` exists for the offline evaluation harness, which drives the real
    prompt and parser without a user's personal configuration (ADR 0018).
    """
    prompt = build_npc_prompt(
        npc_profile,
        player_action=player_action,
        dm_narration=dm_narration,
        psychology=psychology,
        fill_empty_traits=fill_empty_traits,
        language=language,
    )

    provider, model_config = generation or await get_generation()

    try:
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

        return NPCDialogue(
            npc_name=npc_name,
            dialogue=data.get("dialogue", "..."),
            action=data.get("action"),
            axis_changes=_parse_axis_changes(data.get("axis_changes")),
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
    baseline = campaign.world_baseline or {}
    psychology = resolve_psychology(baseline.get("taxonomy"))
    # D2: at rich detail the NPC is told to invent its missing traits in character.
    fill_empty = config.npc_auto_create_detail == "rich"
    language = getattr(campaign, "language", None)
    language = language if isinstance(language, str) else "en"

    tasks = []
    for name in names:
        # Resolve the profile by name/slug (F2 — records are uuid-keyed).
        resolution = resolve_npc(name, {"npcs": npcs_data})
        profile = (
            npcs_data.get(resolution.npc_id, {"name": name})
            if resolution.npc_id
            else {"name": name}
        )
        # Location is a node uuid (J3) — resolve the display name for the prompt.
        node = baseline.get("nodes", {}).get(profile.get("location") or "")
        profile = {**profile, "location_name": (node or {}).get("name")}

        tasks.append(
            invoke_single_npc(
                npc_name=name,
                npc_profile=profile,
                player_action=player_action,
                dm_narration=dm_narration,
                psychology=psychology,
                fill_empty_traits=fill_empty,
                language=language,
            )
        )

    with generation_context(campaign.user_id):
        results = await asyncio.gather(*tasks, return_exceptions=True)

    dialogues = []
    for r in results:
        if isinstance(r, NPCDialogue):
            dialogues.append(r)
        else:
            logger.warning("npc_gather_exception", error=str(r))

    logger.info("npcs_invoked", count=len(dialogues), names=[d.npc_name for d in dialogues])
    return dialogues
