from dataclasses import asdict

from probes import language
from scenario import Scenario

from app.ai.npc_director import invoke_single_npc
from app.ai.prompts.loader import template
from app.ai.prompts.npc import build_npc_prompt
from app.ai.router import ModelConfig
from app.core.npc_resolver import npcs_at_current_location
from app.core.psychology import resolve_psychology


def actor_arguments(scenario: Scenario) -> dict:
    present = npcs_at_current_location(scenario.campaign.world_state)
    npc_id, profile = next(iter(present.items()))
    baseline = scenario.campaign.world_baseline or {}
    node = baseline.get("nodes", {}).get(profile.get("location"), {})
    profile = {**profile, "location_name": node.get("name")}
    return {
        "npc_name": str(profile.get("name") or npc_id),
        "npc_profile": profile,
        "player_action": scenario.stimuli["npc_speaks"].player,
        "dm_narration": scenario.history[-1]["content"] if scenario.history else "",
        "psychology": resolve_psychology(baseline.get("taxonomy")),
        "language": scenario.language,
    }


def actor_request(scenario: Scenario, config: ModelConfig) -> dict:
    args = actor_arguments(scenario)
    name = args.pop("npc_name")
    profile = args.pop("npc_profile")
    return {
        "system_prompt": template("npc", "system").format(name=name),
        "messages": [{"role": "user", "content": build_npc_prompt(profile, **args)}],
        "model": config.model,
        "max_tokens": config.max_tokens,
        "json_mode": True,
    }


async def run_actor(scenario: Scenario) -> tuple[dict, list[str]]:
    result = await invoke_single_npc(**actor_arguments(scenario))
    failed: list[str] = []
    if not isinstance(result.dialogue, str) or result.dialogue.strip() in {"", "...", "…"}:
        failed.append("placeholder")
    elif (detected := language(result.dialogue)) not in {"?", scenario.language}:
        failed.append(f"language:{detected}")
    return asdict(result), failed
