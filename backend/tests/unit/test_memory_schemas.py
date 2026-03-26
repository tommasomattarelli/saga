"""Tests for NPC and Companion Pydantic schemas."""

from app.memory.schemas import CompanionProfile, NPCProfile


class TestNPCProfile:
    def test_defaults(self):
        npc = NPCProfile(name="Grenda")
        assert npc.name == "Grenda"
        assert npc.disposition_toward_player == 0
        assert npc.goals == []
        assert npc.memory == []

    def test_clamp_disposition_high(self):
        npc = NPCProfile(name="X", disposition_toward_player=200)
        assert npc.disposition_toward_player == 100

    def test_clamp_disposition_low(self):
        npc = NPCProfile(name="X", disposition_toward_player=-200)
        assert npc.disposition_toward_player == -100

    def test_extra_fields_allowed(self):
        npc = NPCProfile(name="X", custom_field="test")
        assert npc.custom_field == "test"

    def test_full_profile(self):
        npc = NPCProfile(
            name="Grenda Ironveil",
            role="Blacksmith",
            location="Ironforge Market",
            personality={"traits": ["cautious", "loyal"], "fears": ["the guard captain"]},
            disposition_toward_player=30,
            goals=["keep forge running"],
            memory=["Player bought a sword on turn 5"],
        )
        assert npc.personality.traits == ["cautious", "loyal"]
        assert len(npc.goals) == 1


class TestCompanionProfile:
    def test_inherits_npc(self):
        comp = CompanionProfile(name="Lyra")
        assert comp.loyalty == 50
        assert comp.personal_quest_stage == "dormant"
        assert comp.combat_style == "balanced"

    def test_clamp_loyalty_high(self):
        comp = CompanionProfile(name="X", loyalty=150)
        assert comp.loyalty == 100

    def test_clamp_loyalty_low(self):
        comp = CompanionProfile(name="X", loyalty=-10)
        assert comp.loyalty == 0

    def test_full_companion(self):
        comp = CompanionProfile(
            name="Lyra Starweaver",
            role="Mage",
            loyalty=75,
            opinions={"Kael": "respect", "Brynn": "distrust"},
            combat_style="ranged",
            backstory_hooks=["lost her familiar in the Shadow War"],
        )
        assert comp.opinions["Kael"] == "respect"
        assert len(comp.backstory_hooks) == 1
