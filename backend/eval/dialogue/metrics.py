from dataclasses import asdict, dataclass

from app.core.dialogue_markers import RESERVED_MARKER
from app.core.dm.dialogue_composition import placement_events
from app.core.dm.game_state import GameState
from eval.dialogue.cases import Case
from eval.probes.probes import language
from eval.support.ledger import Attempt


@dataclass
class ActorDispatch:
    npc_id: str | None
    npc_name: str
    step: int | None
    beat: int | None
    observed_beats: str
    status: str | None = None


def language_metric(text: str, target: str) -> dict:
    detected = language(text)
    return {
        "detected": detected,
        "status": f"likely-{target}" if detected == target else "needs-review",
        "review_required": True,
    }


def pipeline_metrics(
    state: GameState,
    responses: list[dict],
    dispatches: list[ActorDispatch],
    attempts: list[Attempt],
    case: Case,
    target_language: str,
) -> dict:
    registry = state["npc_lines"]
    beats = state["npc_beats"]
    raw_text = "\n".join(response["text"] for response in responses)
    public_text = "\n".join(
        part.get("text", "")
        for segment in state["narration_segments"]
        for part in segment.get("parts", [])
        if part.get("type") == "text"
    )
    calls = [
        (response["step"], call)
        for response in responses
        for call in response["tool_calls"]
        if call["name"] == "invoke_npc"
    ]
    target = case.expected_second_npc
    first_step = beats[0].step if beats else None
    second_calls = [
        call
        for step, call in calls
        if first_step is not None
        and step > first_step
        and (target is None or call["args"].get("name", "").casefold() == target.casefold())
    ]
    second_dispatches = [
        item
        for item in dispatches
        if (item.beat or 0) > 0
        and (target is None or item.npc_name.casefold() == target.casefold())
    ]
    observed: list[bool] = []
    for item in second_dispatches:
        prior = [
            f'{result.npc_name}: "{line}"'
            for beat in beats[: item.beat]
            for result in beat.results
            if result.npc_id != item.npc_id
            for line in result.lines
        ]
        observed.append(bool(prior) and all(line in item.observed_beats for line in prior))
    accepted = sum(
        event.line is not None
        for event in placement_events(
            [{"step": response["step"], "text": response["text"]} for response in responses],
            registry,
        )
    )
    narrator_language = language_metric(public_text, target_language)
    actor_languages = [
        {
            "npc_id": result.npc_id,
            "npc_name": result.npc_name,
            "beat": index,
            **language_metric(" ".join([*result.lines, result.action or ""]), target_language),
        }
        for index, beat in enumerate(beats)
        for result in beat.results
    ]
    language_results = [*([narrator_language] if public_text.strip() else []), *actor_languages]
    all_likely = bool(language_results) and all(
        item["status"] == f"likely-{target_language}" for item in language_results
    )
    utterances = {line.part.dialogue for line in registry}
    return {
        "invocations": {
            "requested": len(calls),
            "selected": len(dispatches),
            "executed": len(attempts),
            "succeeded": sum(item.status in {"speaking", "silent"} for item in dispatches),
            "speaking": sum(item.status == "speaking" for item in dispatches),
            "silent": sum(item.status == "silent" for item in dispatches),
            "failed": sum(item.status == "failure" for item in dispatches),
        },
        "actor_calls": [asdict(item) for item in dispatches],
        "second_beat": {
            "expected": target is not None,
            "requested": bool(second_calls),
            "executed": bool(second_dispatches),
            "successful": any(item.status == "speaking" for item in second_dispatches),
            "received_prior_public_lines": any(observed) if observed else None,
        },
        "raw_marker_count": sum(1 for _ in RESERVED_MARKER.finditer(raw_text)),
        "accepted_marker_count": accepted,
        "final_marker_count": sum(1 for _ in RESERVED_MARKER.finditer(public_text)),
        "fallback_speech_parts": max(0, len(registry) - accepted),
        "raw_exact_echo_count": sum(raw_text.count(line) for line in utterances),
        "final_exact_echo_count": sum(public_text.count(line) for line in utterances),
        "echo_counts_are_lexical_not_semantic": True,
        "echo_guard_removals": state.get("dialogue_echo_removals", 0),
        "narrator_language": narrator_language,
        "actor_languages": actor_languages,
        "language_status": f"likely-{target_language}" if all_likely else "needs-review",
        "language_review_required": True,
        "semantic_review_required": case.expected_relevance,
    }
