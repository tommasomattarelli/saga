"""The eval grader decides which model you pick — it must not lie."""

import pytest
from probes import PROBES_BY_NAME, grade, language

_IT = "Il corvo tace. La ranger ti misura con lo sguardo, la mano sul coltello."
_EN = "The raven is silent. She measures you with her eyes and says nothing at all."


@pytest.mark.parametrize(
    ("probe", "text", "called", "expected"),
    [
        ("npc_speaks", _IT, {"invoke_npc"}, []),
        ("npc_speaks", _IT, set(), ["missing:invoke_npc"]),
        ("npc_speaks", _EN, {"invoke_npc"}, ["language:en"]),
        (
            "npc_speaks",
            "Il corvo tace. **Lyra** ti guarda e non dice nulla.",
            {"invoke_npc"},
            ["markdown"],
        ),
        (
            "npc_speaks",
            "Devi superare un DC 15 di Persuasione per convincerla.",
            {"invoke_npc"},
            ["mechanics-leak"],
        ),
        (
            "npc_followup",
            "La nebbia si alza dal muschio. Il sentiero scompare tra i pini.",
            set(),
            [],
        ),
        (
            "npc_followup",
            "Lei ripete piano: «Sei al Santuario della Prima Luce, resto qui».",
            set(),
            ["restates-npc"],
        ),
        ("npc_followup", _IT, {"invoke_npc"}, ["forbidden:invoke_npc"]),
    ],
)
def test_grade_italian_scenario(
    probe: str, text: str, called: set[str], expected: list[str]
) -> None:
    assert grade(PROBES_BY_NAME[probe], text, called, expect_language="it") == expected


def test_expected_language_comes_from_the_scenario() -> None:
    """gold is authored in English. Flagging English there would make the grader
    lie about the exact thing it exists to measure (#51)."""
    assert grade(PROBES_BY_NAME["npc_speaks"], _EN, {"invoke_npc"}, expect_language="en") == []
    assert grade(PROBES_BY_NAME["npc_speaks"], _IT, {"invoke_npc"}, expect_language="en") == [
        "language:it"
    ]


def test_silent_desync_is_labelled_apart_from_a_plain_miss() -> None:
    """Declining the action is unhelpful. Narrating a whole turn as though it
    happened and recording nothing leaves the world disagreeing with what the
    player read, and nothing downstream can see it — the two must not share a label."""
    probe = PROBES_BY_NAME["narration_without_tool"]
    deflected = "Lyra non prende la coperta."
    committed = (
        "Lyra prende la coperta senza dire niente e se la mette sulle spalle, e per un "
        "momento la guarda come se pesasse piu' di quanto pesa. Poi torna a fissare il "
        "sentiero, e la nebbia si chiude sul fondo della valle mentre la luce cala."
    )

    assert grade(probe, deflected, set(), expect_language="it") == ["missing:remove_item"]
    assert grade(probe, committed, set(), expect_language="it") == [
        "narrated-not-called:remove_item"
    ]
    assert grade(probe, committed, {"remove_item"}, expect_language="it") == []


def test_language_detection() -> None:
    assert language(_IT) == "it"
    assert language(_EN) == "en"


def test_empty_narration_is_not_flagged_on_language() -> None:
    """A tool-only step is legal (dm.yaml multi-step rules) — it must not fail here."""
    assert grade(PROBES_BY_NAME["npc_speaks"], "", {"invoke_npc"}, expect_language="it") == []
