"""ADR 0022 P1/P2 — typed recalled-fact rendering and block order."""

import pytest

from app.ai.prompts.dm import (
    DMPromptContext,
    DMPromptState,
    RecalledFact,
    render_dm_prompt,
)
from app.models.quest import QuestRecord, QuestRegistry


def _prompt(*facts: RecalledFact, quests: QuestRegistry | None = None) -> str:
    state = DMPromptState({}, {}, {}, quests or QuestRegistry())
    context = DMPromptContext(recalled_memories=facts)
    return render_dm_prompt(state, context, set())


def _with_quests() -> QuestRegistry:
    return QuestRegistry(
        active=[QuestRecord(id="find_lyra", name="Find Lyra", description="Locate the ranger.")]
    )


def test_recalled_fact_renders_line() -> None:
    fact = RecalledFact(
        content="Lyra kept the old map.",
        category="commitment",
        age_turns=38,
        speaker="Lyra",
        assertion_type="statement",
    )

    assert "  - (38 turns ago · commitment · Lyra said) Lyra kept the old map." in _prompt(fact)


@pytest.mark.parametrize(
    "age_turns,expected",
    [(1, "1 turn ago"), (2, "2 turns ago")],
)
def test_age_is_singular_or_plural(age_turns, expected) -> None:
    assert expected in _prompt(RecalledFact(content="x", age_turns=age_turns))


def test_zero_age_is_omitted() -> None:
    assert "turns ago" not in _prompt(RecalledFact(content="x", age_turns=0))


@pytest.mark.parametrize(
    "assertion_type,verb",
    [("statement", "Marta said"), ("belief", "Marta believed"), ("intention", "Marta intended")],
)
def test_attribution_verb_follows_assertion_type(assertion_type, verb) -> None:
    fact = RecalledFact(content="x", speaker="Marta", assertion_type=assertion_type)

    assert verb in _prompt(fact)


def test_occurrence_has_no_speaker_verb() -> None:
    fact = RecalledFact(content="x", speaker="Marta", assertion_type="occurrence")
    rendered = _prompt(fact)

    assert "Marta said" not in rendered
    assert "Marta believed" not in rendered
    assert "Marta intended" not in rendered


def test_categories_pass_through() -> None:
    rendered = _prompt(RecalledFact(content="x", category="state_change"))

    assert "(state_change)" in rendered


def test_critical_marker_and_ordinary_omission() -> None:
    assert "(information · critical) x" in _prompt(
        RecalledFact(content="x", importance="critical")
    )
    assert "(information · ordinary)" not in _prompt(RecalledFact(content="x"))


def test_content_is_xml_escaped() -> None:
    fact = RecalledFact(content="Lyra & <the guard> said 'no'")

    assert "Lyra &amp; &lt;the guard&gt; said 'no'" in _prompt(fact)


def test_recalled_memories_block_is_last_after_quests() -> None:
    prompt = _prompt(RecalledFact(content="A recalled promise."), quests=_with_quests())

    assert "<quests>" in prompt and "<recalled_memories>" in prompt
    assert prompt.index("<quests>") < prompt.index("<recalled_memories>")
    assert prompt.index("</quests>") < prompt.index("<recalled_memories>")
    assert prompt.endswith("</recalled_memories>")


def test_bare_string_memories_are_no_longer_accepted() -> None:
    state = DMPromptState({}, {}, {}, QuestRegistry())
    context = DMPromptContext(recalled_memories=("legacy bare string",))  # type: ignore[arg-type]

    with pytest.raises(AttributeError):
        render_dm_prompt(state, context, set())
