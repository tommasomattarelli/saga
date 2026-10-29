import pytest

from app.core.dm.dialogue_composition import clean_narration, compose_segments, register_lines


def registry():
    lines = []
    register_lines(lines, "lysa-id", "Lysa", ("Forse", "Non ho la chiave."), step=0, beat=0)
    return lines


@pytest.mark.parametrize("opening,closing", [('"', '"'), ("“", "”"), ("«", "»")])
def test_only_the_whole_quoted_copy_after_its_valid_marker_is_removed(opening, closing):
    text = f"Forse la porta è chiusa. [[npc:Lysa:1]] {opening}Forse{closing}\n\nForse no."
    cleaned, count = clean_narration(text, 1, [], registry())
    assert cleaned == "Forse la porta è chiusa. [[npc:Lysa:1]]\n\nForse no."
    assert count == 1
    assert clean_narration(cleaned, 1, [], registry()) == (cleaned, 0)


@pytest.mark.parametrize(
    "text,step",
    [
        ("[[npc:Lysa:1]] Forse", 1),
        ("«Forse» [[npc:Lysa:1]]", 1),
        ("[[npc:Unknown:1]] «Forse»", 1),
        ("[[npc:Lysa:1]] «Forse»", 0),
        ("[[npc:Lysa:1]] «Forse no»", 1),
        ("[[npc:Lysa:1]] «Forse», dice Neri.", 1),
        ("[[npc:Lysa:1]] «Forse» rispondi tu.", 1),
        ("Neri says: [[npc:Lysa:1]] «Forse»", 1),
        ("Neri says:\n\n[[npc:Lysa:1]] «Forse»", 1),
        ("Neri ripete [[npc:Lysa:1]] «Forse»", 1),
        ("[[npc:Lysa:1]] «Forse».", 1),
        ("«[[npc:Lysa:1]] «Forse»»", 1),
        ('"A quote [[npc:Lysa:1]] «Forse»', 1),
        ("[[npc:Lysa:1]] «Forse", 1),
    ],
)
def test_ambiguous_nonquoted_invalid_or_different_speech_is_preserved(text, step):
    assert clean_narration(text, step, [], registry()) == (text, 0)


def test_repeated_marker_does_not_authorize_deleting_another_quote():
    previous = [{"step": 1, "text": "[[npc:Lysa:1]]", "dice": {"total": 12}}]
    text = "[[npc:Lysa:1]] «Forse»"
    assert clean_narration(text, 2, previous, registry()) == (text, 0)


def test_composition_uses_the_same_guard_and_never_changes_the_frozen_bubble():
    segments = compose_segments(
        [{"step": 1, "text": '[[npc:Lysa:2]] "Non ho la chiave."', "dice": None}], registry()
    )
    speech = [p.dialogue for s in segments for p in s.parts if p.type == "npc_speech"]
    text = "".join(p.text for s in segments for p in s.parts if p.type == "text")
    assert speech == ["Non ho la chiave.", "Forse"]
    assert "Non ho la chiave." not in text
