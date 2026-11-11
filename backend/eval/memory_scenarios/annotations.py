from pydantic import JsonValue

from eval.memory_scenarios.chapters import PLAYER_NAME
from eval.memory_scenarios.timeline import CHAPTERS


def build_annotations(chapter_annotations: list[JsonValue], npc_name: str) -> dict[str, JsonValue]:
    turns = {chapter.key: index for index, chapter in enumerate(CHAPTERS, start=1)}
    return {
        "name": "adr0020-controlled-long-source",
        "synthetic": True,
        "dataset_kind": "controlled_synthetic_fixture",
        "evidence_role": "longitudinal test input; not a real campaign",
        "world": "the-awakening",
        "chapters": chapter_annotations,
        "anchors": {
            "promise_turn": turns["promise"],
            "belief_turn": turns["clue-belief"],
            "key_recovery_turn": turns["key-recovery"],
            "resolution_turn": turns["fulfilment"],
            "belief_speaker": PLAYER_NAME,
            "resolution_npc": npc_name,
        },
        "expected_threads": {
            "sealed_key": {
                "opened_turn": turns["promise"],
                "resolution_turn": turns["fulfilment"],
                "before_resolution": "open",
                "after_resolution": "closed",
            },
            "ash_mark": {
                "belief_turn": turns["clue-belief"],
                "attributed_to": PLAYER_NAME,
                "after_resolution": "unverified",
            },
            "ferry_manifest": {
                "opened_turn": turns["smuggler-warning"],
                "after_resolution": "open",
                "attributed_warning_source": npc_name,
            },
        },
        "full_speech_turns": [
            index
            for index, chapter in enumerate(CHAPTERS, start=1)
            if chapter.npc is None and any(call.name == "invoke_npc" for call in chapter.calls)
        ],
        "silent_turns": [
            index for index, chapter in enumerate(CHAPTERS, start=1) if chapter.npc == "silent"
        ],
        "quest_status_chronology": ["active", "completed", "active", "completed"],
    }
