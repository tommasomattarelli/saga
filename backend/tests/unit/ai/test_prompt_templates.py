from hashlib import sha256

import pytest

from app.ai.prompts import loader
from app.ai.tools.dm_tools import get_tool, get_tool_schemas


def test_template_names_and_values_are_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "TEMPLATE_DIR", tmp_path)
    loader.load_templates.cache_clear()
    (tmp_path / "broken.yaml").write_text("a: 3\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="non-empty text"):
            loader.load_templates("broken")
        with pytest.raises(ValueError, match="template name"):
            loader.load_templates("../broken")
        with pytest.raises(ValueError, match="missing"):
            loader.template("missing", "system")
    finally:
        loader.load_templates.cache_clear()


def test_all_registered_tools_have_known_obligations_and_explicit_loop_policy():
    from app.ai.prompts.obligations import compose_obligations

    blocks = loader.load_templates("tool_obligations")
    for schema in get_tool_schemas():
        name = schema["function"]["name"]
        tool = get_tool(name)
        assert tool is not None
        assert tool.obligation in blocks
        assert isinstance(tool.terminal_safe, bool)
        assert f'tool="{name}"' in compose_obligations({name})


def test_obligation_composition_is_exact_and_deterministic():
    from app.ai.prompts.obligations import compose_obligations

    first = compose_obligations({"move_to", "add_item"})
    assert first == compose_obligations(set(reversed(["move_to", "add_item"])))
    assert first.index('tool="add_item"') < first.index('tool="move_to"')
    assert 'tool="invoke_npc"' not in first
    with pytest.raises(ValueError, match="Unknown tool"):
        compose_obligations({"bogus"})


def test_filtered_prompt_and_schemas_have_the_same_obligations():
    from app.ai.prompts.dm import build_dm_system_prompt
    from app.models.campaign import Campaign

    campaign = Campaign(world_state={}, character_data={}, quests={}, language="en")
    allowed = {"advance_time", "set_scene_mood", "log_event"}
    prompt = build_dm_system_prompt(campaign, allowed_tools=allowed, closing=True)
    for schema in get_tool_schemas():
        name = schema["function"]["name"]
        assert (f'tool="{name}"' in prompt) == (name in allowed)
    assert "CLOSING STEP" in prompt
    assert "FIRST response: write your full narration" not in prompt


@pytest.mark.parametrize("closing", [False, True])
def test_current_state_authority_is_explicit_without_erasing_historical_context(closing):
    from app.ai.prompts.dm import build_dm_system_prompt
    from app.models.campaign import Campaign

    campaign = Campaign(world_state={}, character_data={}, quests={}, language="en")
    summary = "Earlier narration placed the player in Thornhaven."
    memory = "The player previously reached the village gate."
    prompt = build_dm_system_prompt(
        campaign,
        summary_context=summary,
        recalled_memories=[memory],
        allowed_tools={"advance_time"} if closing else {"move_to"},
        closing=closing,
    )

    assert "CURRENT STATE IS AUTHORITATIVE:" in prompt
    assert (
        "override conflicting earlier assistant messages, summaries and recalled memories"
        in prompt
    )
    assert "Do not say the player is already there based on history alone" in prompt
    assert prompt.index("CURRENT STATE IS AUTHORITATIVE:") < prompt.index("<history label=")
    assert summary in prompt and memory in prompt
    assert ('tool="move_to"' in prompt) is not closing


def test_movement_obligation_uses_canonical_location_when_history_claims_arrival():
    from app.ai.prompts.obligations import compose_obligations

    obligation = compose_obligations({"move_to"})
    assert (
        "Compare the destination with the current canonical location, not earlier prose"
        in obligation
    )
    assert "still resolve the requested journey with move_to" in obligation


def test_unknown_obligation_reference_is_rejected(monkeypatch):
    from app.ai.prompts.obligations import compose_obligations

    tool = get_tool("move_to")
    assert tool is not None
    monkeypatch.setattr(tool, "obligation", "nonexistent")
    with pytest.raises(ValueError, match="nonexistent"):
        compose_obligations({"move_to"})


@pytest.mark.parametrize(
    "file,key,digest",
    [
        (
            "fact_extractor",
            "base",
            "12ef0e025d8e315e74316030befec480b4e7af93f8eeb159c0f448649a75409f",
        ),
        ("compressor", "base", "24e0bab0c737be75f425d381be7bfb56c034f50e5e935643a8f79c8f4d8ca04d"),
        (
            "global_summary",
            "initial",
            "126fe3f5eb5ae8e0f3aeb9e6bb91111e0a9118b3bd13e2790760d0e87191df90",
        ),
        (
            "global_summary",
            "update",
            "71db4a75ef6a84ac0057387276e1621d475c99cc1d140e1bc7dd2f123b40be2b",
        ),
        ("npc", "base", "53a4e0a34a5025cd61b41747fcaad679e21651651b2ff5f3fff49aceccdf92f5"),
        (
            "personas",
            "grimdark",
            "c7f4a30f76052f324542ed3f3b2dde04fe7665dcb095557d8fed4b19085028bc",
        ),
        ("personas", "heroic", "d10906de698b78254b8272b3705a4793a8165486626ea6844feb3845f08a5287"),
        (
            "personas",
            "dark_fantasy",
            "a9f58e93186af02eea478ddba62337973344789f07eb40d0b8b65a10ea68fabb",
        ),
        ("personas", "horror", "cd2cb764dc9926a936334e49ab3b42cbe1a3356d858163d28b585a53ba04858f"),
    ],
)
def test_extracted_text_is_byte_identical_to_pre_extraction(file, key, digest):
    assert sha256(loader.template(file, key).encode()).hexdigest() == digest
