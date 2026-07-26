"""The smoke harness grader decides which model you pick — it must not lie."""

import pytest
from model_smoke import SCENARIOS, _grade, _language

_BY_NAME = {s.name: s for s in SCENARIOS}

_IT = "Il corvo tace. La ranger ti misura con lo sguardo, la mano sul coltello."
_EN = "The raven is silent. She measures you with her eyes and says nothing at all."


@pytest.mark.parametrize(
    ("scenario", "text", "called", "expected"),
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
def test_grade(scenario: str, text: str, called: set[str], expected: list[str]) -> None:
    assert _grade(_BY_NAME[scenario], text, called) == expected


def test_language_detection() -> None:
    assert _language(_IT) == "it"
    assert _language(_EN) == "en"


def test_empty_narration_is_not_flagged_as_english() -> None:
    """A tool-only step is legal (dm.yaml multi-step rules) — it must not fail on language."""
    assert _grade(_BY_NAME["npc_speaks"], "", {"invoke_npc"}) == []
