import json
import uuid
from dataclasses import asdict

from actor_probe import actor_arguments
from dialogue_conversation import run_conversation
from dialogue_pipeline import initial_state, run_pipeline
from dialogue_requests import SuiteProvider
from live_calls import dm_request
from probes import PROBES_BY_NAME, grade, language
from scenario import Scenario

from app.ai.generation_context import generation_context
from app.ai.npc_director import invoke_single_npc
from app.ai.npc_outcomes import NPCSilent, NPCSpeaking
from app.ai.prompts.dm import campaign_prompt_context
from app.ai.router import ModelConfig
from app.core.dialogue_markers import RESERVED_MARKER, strip_markers
from app.core.dm.dialogue_composition import (
    clean_narration,
    compose_segments,
    placement_events,
    register_lines,
    transcript,
)
from app.core.dm.dm_nodes import step_system_prompt
from app.core.dm.npc_context import NPCBeat, PublicNPCResult
from app.core.npc_resolver import npcs_at_current_location, resolve_npc


async def run_case(
    case: str,
    sc: Scenario,
    trace: SuiteProvider,
    config: ModelConfig,
    user_id: uuid.UUID,
) -> tuple[dict, list[str]]:
    if case == "two_npc_conversation":
        return await run_conversation(sc, trace, config, user_id)
    if case in {"two_npc_two_beat", "two_npc_natural"}:
        return await run_pipeline(sc, trace, config, user_id)
    if case.startswith("actor_"):
        arguments = actor_arguments(sc)
        if case == "actor_scene":
            current = sc.campaign.world_state.get("meta", {}).get("current_location")
            _, profile = next(
                (key, npc)
                for key, npc in sc.campaign.world_state.get("npcs", {}).items()
                if npc.get("lifecycle") == "alive" and npc.get("location") == current
            )
            node = (sc.campaign.world_baseline or {}).get("nodes", {}).get(current, {})
            arguments["scene_context"] = json.dumps(
                {
                    "location": node.get("name"),
                    "condition": profile.get("condition"),
                    "hp": profile.get("hp"),
                    "player": {
                        key: sc.campaign.character_data.get(key)
                        for key in ("name", "hp", "inventory")
                    },
                },
                ensure_ascii=False,
            )
            arguments["observed_beats"] = ""
        with generation_context((trace, config)):
            result = await invoke_single_npc(**arguments)
        expected = NPCSilent if case == "actor_silent" else NPCSpeaking
        failed = [] if isinstance(result, expected) else ["unexpected-actor-outcome"]
        detected = "?"
        if isinstance(result, NPCSpeaking | NPCSilent):
            detected = language(" ".join([*result.lines, result.action or ""]))
            if detected not in {"?", sc.language}:
                failed.append(f"language:{detected}")
        return {
            "actor": asdict(result),
            "target_language": sc.language,
            "metrics": {
                "requests": {
                    "requested": 1,
                    "executed": trace.count,
                    "succeeded": int(trace.count > 0 and not trace.errors),
                    "failed": int(trace.errors),
                },
                "actor_valid": isinstance(result, NPCSpeaking | NPCSilent),
                "actor_expected_outcome": isinstance(result, expected),
                "actor_status": result.status
                if isinstance(result, NPCSpeaking | NPCSilent)
                else "failure",
                "language_heuristic": detected,
                "language_status": (
                    f"likely-{sc.language}" if detected == sc.language else "needs-review"
                ),
                "language_review_required": True,
            },
        }, failed
    probe = "npc_followup" if case in {"npc_followup", "npc_followup_short"} else case
    request = dm_request(sc, probe, config)
    state = initial_state(sc, user_id)
    state["prompt_context"] = campaign_prompt_context(
        sc.campaign, sc.summary_context, sc.global_summary, sc.recalled_memories(probe)
    )
    registry = []
    if case in {"npc_followup", "npc_followup_short"}:
        stimulus = sc.stimuli[probe]
        npc_id = resolve_npc(stimulus.npc_name, sc.campaign.world_state).npc_id
        if npc_id is None:
            raise ValueError("The injected actor must exist in the scenario.")
        lines = register_lines(
            registry, npc_id, stimulus.npc_name, (stimulus.npc_dialogue,), step=0, beat=0
        )
        state["step_count"] = 1
        state["npc_lines"] = registry
        location = sc.campaign.world_state.get("meta", {}).get("current_location", "")
        state["npc_beats"] = [
            NPCBeat(
                step=0,
                observers=frozenset(npcs_at_current_location(sc.campaign.world_state)),
                location=location,
                results=(
                    PublicNPCResult(
                        npc_id,
                        stimulus.npc_name,
                        (stimulus.npc_dialogue,),
                        stimulus.npc_action or None,
                    ),
                ),
            )
        ]
        request["messages"][-1]["content"] = (
            f"{lines[0].handle} {stimulus.npc_dialogue}\nDescriptive action/intention: {stimulus.npc_action}"
        )
    allowed_tools = {tool["function"]["name"] for tool in request["tools"]}
    request["system_prompt"] = step_system_prompt(state, allowed_tools, False)
    response = await trace.generate_with_tools(**request)
    failed = grade(
        PROBES_BY_NAME[probe],
        strip_markers(response.text),
        {call.name for call in response.tool_calls},
        sc.language,
    )
    segments = compose_segments([{"step": 1, "text": response.text, "dice": None}], registry)
    final_narration = transcript(segments)
    final_text, guard_removals = clean_narration(response.text, 1, [], registry)
    accepted_markers = sum(
        event.line is not None
        for event in placement_events([{"step": 1, "text": response.text}], registry)
    )
    if registry and not any(
        s.step == 1 and any(p.type == "npc_speech" for p in s.parts) for s in segments
    ):
        failed.append("line-used-end-fallback")
    return {
        "response": {
            "text": response.text,
            "tool_calls": [asdict(call) for call in response.tool_calls],
        },
        "parts": [segment.model_dump(mode="json") for segment in segments],
        "narration": final_narration,
        "target_language": sc.language,
        "metrics": {
            "requests": {
                "requested": 1,
                "executed": trace.count,
                "succeeded": int(trace.count > 0 and not trace.errors),
                "failed": int(trace.errors),
            },
            "actor_valid": None,
            "raw_echo_exact": int(stimulus.npc_dialogue in response.text)
            if case in {"npc_followup", "npc_followup_short"}
            else 0,
            "final_echo_exact": int(stimulus.npc_dialogue in final_text)
            if case in {"npc_followup", "npc_followup_short"}
            else 0,
            "echo_guard_removals": guard_removals,
            "language_heuristic": language(strip_markers(final_text)),
            "language_status": (
                f"likely-{sc.language}"
                if language(strip_markers(final_text)) == sc.language
                else "needs-review"
            ),
            "language_review_required": True,
            "raw_marker_count": sum(1 for _ in RESERVED_MARKER.finditer(response.text)),
            "fallback_speech_parts": max(0, len(registry) - accepted_markers),
            "fallback_used": bool(registry) and len(registry) > accepted_markers,
            "accepted_marker_count": accepted_markers,
            "final_marker_count": sum(1 for _ in RESERVED_MARKER.finditer(final_narration)),
        },
    }, failed
