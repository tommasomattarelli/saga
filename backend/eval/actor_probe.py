"""Bounded real-actor path for live evaluation.

The DM probes inject an actor result, so they cannot see the failure #51 reports:
the actor's own prompt decides its language. This path runs the real
`invoke_single_npc` (real prompt, real parser, real failure fallback) against one
present, living NPC and grades the returned line.

One call per run: the path is bounded on purpose. Batched beats and multi-line
results belong to ADR 0017 and are measured by PR 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from probes import language

from app.ai.npc_director import invoke_single_npc
from app.ai.providers.base import get_provider
from app.core.npc_resolver import npcs_at_current_location
from app.core.psychology import resolve_psychology

PLACEHOLDERS = {"", "...", "…"}


@dataclass
class ActorOutcome:
    npc: str
    dialogue: str
    failed: list[str] = field(default_factory=list)
    error: str = ""


async def run_actor(
    *,
    provider_name: str,
    model: str,
    max_tokens: int,
    scenario,
    player_action: str,
    dm_narration: str,
) -> ActorOutcome:
    present = npcs_at_current_location(scenario.campaign.world_state)
    if not present:
        return ActorOutcome(npc="", dialogue="", failed=["no-present-npc"])

    npc_id, profile = next(iter(present.items()))
    npc_name = str(profile.get("name") or npc_id)
    baseline = scenario.campaign.world_baseline or {}
    psychology = resolve_psychology((baseline.get("taxonomy") or {}).get("psychology"))

    try:
        result = await invoke_single_npc(
            npc_name=npc_name,
            npc_profile=profile,
            player_action=player_action,
            dm_narration=dm_narration,
            psychology=psychology,
            generation=(
                get_provider(provider_name),
                SimpleNamespace(model=model, max_tokens=max_tokens),
            ),
        )
    except Exception as exc:  # a failing provider is a result, not a crash (#50)
        return ActorOutcome(npc=npc_name, dialogue="", failed=["error"], error=str(exc)[:160])

    failed: list[str] = []
    if result.dialogue.strip() in PLACEHOLDERS:
        failed.append("placeholder")
    else:
        detected = language(result.dialogue)
        if detected != "?" and detected != scenario.language:
            failed.append(f"language:{detected}")

    return ActorOutcome(npc=npc_name, dialogue=result.dialogue, failed=failed)
