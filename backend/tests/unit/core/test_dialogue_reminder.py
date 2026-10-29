import json
from html import unescape

from app.core.dm.dialogue_composition import register_lines
from app.core.dm.dialogue_reminder import dialogue_reminder
from app.core.dm.npc_context import NPCBeat, PublicNPCResult


def test_reminder_uses_the_same_valid_placements_and_only_public_beat_identity():
    registry = []
    register_lines(registry, "id", "Lysa", ("PRIVATE_WORDS", "Other words."), step=0, beat=0)
    beats = [
        NPCBeat(
            0,
            frozenset({"id"}),
            "place",
            (PublicNPCResult("id", "Lysa", ("PRIVATE_WORDS",), "PRIVATE_ACTION"),),
        )
    ]
    segments = [
        {"step": 0, "text": "[[npc:Lysa:2]]"},
        {"step": 1, "text": "[[npc:Lysa:1]] [[npc:Lysa:1]] [[npc:Unknown:2]]"},
    ]
    reminder = dialogue_reminder(registry, beats, segments, "it", False)
    payload = reminder.split("<dialogue_state>")[1].split("</dialogue_state>")[0]
    data = json.loads(unescape(payload))
    assert data["available_handles"] == ["[[npc:Lysa:1]]", "[[npc:Lysa:2]]"]
    assert data["unplaced_handles"] == ["[[npc:Lysa:2]]"]
    assert data["completed_beats"] == [{"step": 0, "actors": ["Lysa"]}]
    assert "PRIVATE_WORDS" not in reminder and "PRIVATE_ACTION" not in reminder
    assert "Italian (it)" in reminder


def test_closing_and_empty_failure_beat_do_not_invent_silence_or_force_reaction():
    reminder = dialogue_reminder([], [NPCBeat(0, frozenset(), "place", ())], [], "ja", True)
    assert "No further actor calls" in reminder
    assert "Reactions to new words may use a subsequent beat" not in reminder
    assert "Empty results do not prove intentional silence" in reminder
    assert "Japanese (ja)" in reminder
