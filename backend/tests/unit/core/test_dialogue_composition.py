import pytest

from app.core.dm.dialogue_composition import compose_segments, register_lines, transcript


def test_handles_are_monotonic_frozen_and_insert_each_line_once():
    registry = []
    register_lines(registry, "id-lyra", "Lyra", ("First.", "Second."), step=0, beat=0)
    register_lines(registry, "id-lyra", "Renamed", ("Third.",), step=2, beat=1)
    segments = compose_segments(
        [
            {"step": 0, "text": "Before [[npc:Lyra:1]]", "dice": None},
            {"step": 1, "text": "Wind. [[NPC: lyra :1]] Rain. [[npc:Lyra:1]]", "dice": None},
            {"step": 3, "text": "[[npc:Lyra:3]]", "dice": None},
        ],
        registry,
    )
    parts = [part for segment in segments for part in segment.parts]
    speech = [part for part in parts if part.type == "npc_speech"]
    assert [p.dialogue for p in speech] == ["First.", "Third.", "Second."]
    assert [p.line_index for p in speech] == [1, 3, 2]
    assert speech[0].npc_id == "id-lyra" and speech[2].npc_name == "Lyra"
    assert segments[-1].step == 4
    assert "[[" not in transcript(segments)


@pytest.mark.parametrize(
    "marker",
    [
        "[[npc:Lyra:99]]",
        "[[npc:Lira:1]]",
        "[[npc:Lyra:1",
        "[[npc:Lyra:",
        "[[npc",
        "[[NPC:Lyra:no]]",
        "[[npc:Lyra:1]",
        "[[npc:Lyra:01]]",
    ],
)
def test_invalid_and_incomplete_markers_are_removed_without_losing_real_lines(marker):
    registry = []
    register_lines(registry, "id", "Lyra", ("Actual speech.",), step=0, beat=0)
    segments = compose_segments(
        [
            {
                "step": 1,
                "text": f"Normal [brackets] and [[ordinary]]. {marker}\nNext paragraph.",
                "dice": None,
            }
        ],
        registry,
    )
    result = transcript(segments)
    assert "Normal [brackets] and [[ordinary]]." in result
    assert "Next paragraph." in result
    assert result.count("Actual speech.") == 1
    assert "[[npc" not in result.lower()


def test_colliding_and_reserved_names_have_unambiguous_labels():
    registry = []
    register_lines(registry, "one", "Guard", ("One.",), step=0, beat=0, ambiguous_names={"guard"})
    register_lines(registry, "two", "Guard", ("Two.",), step=0, beat=0, ambiguous_names={"guard"})
    register_lines(registry, "three", "A:[[npc:bad:1]]", ("Three.",), step=0, beat=0)
    assert len({line.handle.casefold() for line in registry}) == 3
    text = " ".join(line.handle for line in reversed(registry))
    result = compose_segments([{"step": 1, "text": text, "dice": None}], registry)
    assert [p.npc_id for p in result[0].parts if p.type == "npc_speech"] == [
        "three",
        "two",
        "one",
    ]
    assert "[[npc" not in transcript(result).lower()


def test_unplaced_lines_are_after_the_last_dice_boundary():
    registry = []
    register_lines(registry, "id", "Lyra", ("After the roll.",), step=1, beat=0)
    dice = {"Check": {"total": 18}}
    segments = compose_segments(
        [
            {"step": 0, "text": "An attempt.", "dice": dice},
            {"step": 1, "text": "A consequence.", "dice": None},
        ],
        registry,
    )
    assert segments[0].dice == dice
    assert segments[-1].step == 2
    assert segments[-1].parts[0].dialogue == "After the roll."
    assert "npc_dialogues" not in segments[-1].model_dump()
    assert "text" not in segments[-1].model_dump()
