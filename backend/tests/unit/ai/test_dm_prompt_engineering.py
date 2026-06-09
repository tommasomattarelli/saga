"""PR3 — Prompt Engineering tests (C4, I1, I3, I4, I5, I6)."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_campaign(**overrides) -> MagicMock:
    campaign = MagicMock()
    campaign.world_state = {}
    campaign.character_data = {}
    campaign.quests = {}
    campaign.death_mode = None
    campaign.persona_preset = None
    campaign.persona_xml = None
    campaign.global_summary = None
    for k, v in overrides.items():
        setattr(campaign, k, v)
    return campaign


# ── I1 — Persona presets ──────────────────────────────────────────────────────

class TestPersonaPresets:
    def test_persona_preset_grimdark_injects_block(self):
        """grimdark preset produces a <persona> block in the system prompt."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign(persona_preset="grimdark")
        prompt = build_dm_system_prompt(campaign)

        assert "<persona>" in prompt
        assert "cruelty" in prompt.lower() or "futility" in prompt.lower()

    def test_persona_preset_heroic_injects_block(self):
        """heroic preset produces a <persona> block mentioning courage/epic."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign(persona_preset="heroic")
        prompt = build_dm_system_prompt(campaign)

        assert "<persona>" in prompt
        assert "epic" in prompt.lower() or "courage" in prompt.lower() or "heroic" in prompt.lower()

    def test_persona_preset_horror_injects_block(self):
        """horror preset produces a <persona> block mentioning dread."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign(persona_preset="horror")
        prompt = build_dm_system_prompt(campaign)

        assert "<persona>" in prompt
        assert "dread" in prompt.lower() or "fear" in prompt.lower()

    def test_persona_xml_override_wins_over_preset(self):
        """Custom persona_xml takes precedence over persona_preset."""
        from app.ai.prompts.dm import build_dm_system_prompt

        custom_xml = "<persona>You are a pirate narrator. Arr.</persona>"
        campaign = _make_campaign(persona_preset="grimdark", persona_xml=custom_xml)
        prompt = build_dm_system_prompt(campaign)

        assert "pirate narrator" in prompt
        assert "brutal" not in prompt.lower() or prompt.index("pirate") < prompt.index("<instructions>")

    def test_no_preset_injects_no_persona_block(self):
        """Without a preset, no <persona> block appears."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign(persona_preset=None, persona_xml=None)
        prompt = build_dm_system_prompt(campaign)

        assert "<persona>" not in prompt

    def test_persona_block_appears_before_instructions(self):
        """<persona> block is injected BEFORE <instructions>."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign(persona_preset="dark_fantasy")
        prompt = build_dm_system_prompt(campaign)

        assert prompt.index("<persona>") < prompt.index("<instructions>")

    def test_all_four_presets_defined(self):
        """All 4 expected persona keys are present in PERSONA_PRESETS."""
        from app.ai.prompts.presets import PERSONA_PRESETS

        assert "grimdark" in PERSONA_PRESETS
        assert "heroic" in PERSONA_PRESETS
        assert "dark_fantasy" in PERSONA_PRESETS
        assert "horror" in PERSONA_PRESETS


# ── C4 — history label ────────────────────────────────────────────────────────

class TestHistoryLabel:
    def test_history_block_has_story_so_far_label(self):
        """<history> tag includes label='story_so_far' attribute."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign()
        prompt = build_dm_system_prompt(campaign, summary_context="Previously, the hero fought.")

        assert 'label="story_so_far"' in prompt
        assert "<history label=" in prompt

    def test_no_history_block_when_summary_empty(self):
        """No history block if summary_context is empty."""
        from app.ai.prompts.dm import build_dm_system_prompt

        campaign = _make_campaign()
        prompt = build_dm_system_prompt(campaign, summary_context="")

        assert "<history" not in prompt


# ── I3 — Empty/gibberish handler ─────────────────────────────────────────────

class TestEmptyInputHandler:
    def test_base_prompt_contains_gibberish_instruction(self):
        """BASE_DM_PROMPT contains instruction for empty/incoherent player input."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        lower = BASE_DM_PROMPT.lower()
        assert "empty" in lower or "incoherent" in lower or "untranslatable" in lower

    def test_instruction_says_describe_scene_passively(self):
        """The empty-input instruction mandates passive scene description."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        assert "passively" in BASE_DM_PROMPT or "perceives" in BASE_DM_PROMPT


# ── I4 — Multi-NPC sequential guidance ───────────────────────────────────────

class TestMultiNpcGuidance:
    def test_base_prompt_contains_one_npc_at_a_time_rule(self):
        """BASE_DM_PROMPT mandates sequential invoke_npc calls."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        lower = BASE_DM_PROMPT.lower()
        assert "one" in lower and ("at a time" in lower or "sequentially" in lower)


# ── I5 — update_quest status enum ────────────────────────────────────────────

class TestUpdateQuestEnum:
    def test_update_quest_tool_documents_all_statuses(self):
        """update_quest status field description includes all 4 valid values."""
        from app.ai.tools.dm_tools import UpdateQuest

        schema = UpdateQuest.to_openai_schema()
        status_desc = schema["function"]["parameters"]["properties"]["status"]["description"]

        for expected in ("active", "completed", "failed", "abandoned"):
            assert expected in status_desc

    def test_update_quest_description_in_base_prompt(self):
        """BASE_DM_PROMPT mentions update_quest in tool guidance."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        assert "update_quest" in BASE_DM_PROMPT


# ── I6 — Backstop rule ───────────────────────────────────────────────────────

class TestBackstopRule:
    def test_backstop_rule_present_in_base_prompt(self):
        """BASE_DM_PROMPT contains the backstop rule about matching tool calls."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        lower = BASE_DM_PROMPT.lower()
        assert "backstop" in lower or ("every" in lower and "tool call" in lower)

    def test_backstop_mentions_no_narration_only_changes(self):
        """Backstop rule explicitly prohibits narration-only state changes."""
        from app.ai.prompts.dm import BASE_DM_PROMPT

        assert "narration-only" in BASE_DM_PROMPT or "No narration" in BASE_DM_PROMPT
