import uuid
from dataclasses import asdict

from actor_probe import actor_arguments
from dialogue_pipeline import run_pipeline
from dialogue_requests import SuiteProvider
from live_calls import dm_request
from probes import PROBES_BY_NAME, grade, language
from scenario import Scenario

from app.ai.generation_context import generation_context
from app.ai.npc_director import invoke_single_npc
from app.ai.npc_outcomes import NPCSilent, NPCSpeaking
from app.ai.router import ModelConfig
from app.core.dialogue_markers import strip_markers
from app.core.dm.dialogue_composition import compose_segments, register_lines, transcript
from app.core.npc_resolver import resolve_npc


async def run_case(
    case: str,
    sc: Scenario,
    trace: SuiteProvider,
    config: ModelConfig,
    user_id: uuid.UUID,
) -> tuple[dict, list[str]]:
    if case == "two_npc_two_beat":
        return await run_pipeline(sc, trace, config, user_id)
    if case.startswith("actor_"):
        with generation_context((trace, config)):
            result = await invoke_single_npc(**actor_arguments(sc))
        expected = NPCSilent if case == "actor_silent" else NPCSpeaking
        failed = [] if isinstance(result, expected) else ["unexpected-actor-outcome"]
        if isinstance(result, NPCSpeaking | NPCSilent):
            detected = language(" ".join([*result.lines, result.action or ""]))
            if detected not in {"?", sc.language}:
                failed.append(f"language:{detected}")
        return {"actor": asdict(result), "target_language": sc.language}, failed
    request = dm_request(sc, case, config)
    registry = []
    if case == "npc_followup":
        stimulus = sc.stimuli[case]
        npc_id = resolve_npc(stimulus.npc_name, sc.campaign.world_state).npc_id
        if npc_id is None:
            raise ValueError("The injected actor must exist in the scenario.")
        lines = register_lines(
            registry, npc_id, stimulus.npc_name, (stimulus.npc_dialogue,), step=0, beat=0
        )
        request["messages"][-1]["content"] = (
            f"{lines[0].handle} {stimulus.npc_dialogue}\nDescriptive action/intention: {stimulus.npc_action}"
        )
    response = await trace.generate_with_tools(**request)
    failed = grade(
        PROBES_BY_NAME[case],
        strip_markers(response.text),
        {call.name for call in response.tool_calls},
        sc.language,
    )
    segments = compose_segments([{"step": 1, "text": response.text, "dice": None}], registry)
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
        "narration": transcript(segments),
        "target_language": sc.language,
    }, failed
