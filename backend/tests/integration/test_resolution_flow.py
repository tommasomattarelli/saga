"""The unified resolver over a real campaign and a real DB (ADR 0003 S1, §G).

Out-of-combat checks are the point of S1: before this ADR `request_dice` sat in a
combat-gated tool group, so lockpicking and persuasion had no mechanic at all.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.core.dm.dm_tools_executor import tools_node
from app.models.campaign import Campaign


async def _create_campaign(auth_client) -> str:
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Resolution Campaign",
            "death_mode": "destino",
            "character_data": {
                "name": "Eron",
                "hp": {"current": 40, "max": 40},
                "abilities": {"dexterity": 16, "charisma": 8},
            },
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _load(db_session, campaign_id: str) -> Campaign:
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    return result.scalar_one()


def _state(campaign: Campaign, tool_call: dict) -> dict:
    return {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "world_state": campaign.world_state,
        "char_data": campaign.character_data,
        "player_action": "",
        "campaign_id": str(campaign.id),
        "narration": "The lock resists.",
        "step_count": 1,
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "system_prompt": "",
        "model_config": {},
        "model_used": "test-model",
        "importance_score": 5,
        "death_event": None,
        "world_baseline": campaign.world_baseline,
    }


def _call(name: str, **args) -> dict:
    return {"id": "tc1", "name": name, "args": args, "type": "tool_call"}


@pytest.mark.asyncio
async def test_a_lockpicking_check_resolves_with_no_combat_in_sight(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))
    assert not campaign.world_state.get("combat_state", {}).get("active")

    result = await tools_node(
        _state(campaign, _call("request_dice", check="lockpicking", stat="DEX", difficulty="hard"))
    )

    roll = result["dice_results"][0]["rolls"]["Lockpicking"]
    assert roll["difficulty"] == "hard"
    assert -5 <= roll["difficulty_draw"] <= -1
    assert roll["modifier"] == 3  # dexterity 16 → (16-10)//2
    assert roll["outcome"] in {
        "critical_failure",
        "hard_failure",
        "soft_failure",
        "partial_success",
        "full_success",
        "critical_success",
    }
    assert "dc" not in roll


@pytest.mark.asyncio
async def test_a_persuasion_check_reads_the_stat_the_frontend_persisted(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))

    result = await tools_node(
        _state(
            campaign,
            _call("request_dice", check="persuasion", stat="CHA", difficulty="very_hard"),
        )
    )

    roll = result["dice_results"][0]["rolls"]["Persuasion"]
    assert roll["modifier"] == -1  # charisma 8 → (8-10)//2
    assert -8 <= roll["difficulty_draw"] <= -4


@pytest.mark.asyncio
async def test_a_failed_trap_reaction_bites_a_share_of_max_hp(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))

    with (
        patch("app.core.dice.random.randint", return_value=1),
        patch("app.core.health.random.uniform", return_value=0.50),
    ):
        result = await tools_node(
            _state(
                campaign,
                _call(
                    "request_dice",
                    check="dodge",
                    stat="DEX",
                    difficulty="hard",
                    hazard_class="deadly",
                ),
            )
        )

    # natural 1 → critical_failure → 1.5x the 50% draw of a 40 HP pool
    assert result["dice_results"][0]["rolls"]["Dodge"]["hazard_damage"] == 30
    assert result["char_data"]["hp"]["current"] == 10


@pytest.mark.asyncio
async def test_healing_lands_and_spends_the_daily_budget(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))
    campaign.character_data["hp"]["current"] = 4

    result = await tools_node(
        _state(campaign, _call("heal", healer="Eron", target="Eron", heal_class="full"))
    )

    assert result["char_data"]["hp"]["current"] == 40
    assert result["world_state"]["dm_heals"]["used"] == 1


@pytest.mark.asyncio
async def test_no_removed_tool_can_write_a_free_hp_number(auth_client, db_session):
    """The ADR 0003 §G regression: leak #2 stays closed."""
    campaign = await _load(db_session, await _create_campaign(auth_client))
    campaign.character_data["hp"]["current"] = 4

    result = await tools_node(_state(campaign, _call("update_hp", change=999, reason="jailbreak")))

    assert result["char_data"]["hp"]["current"] == 4
    assert "unknown tool" in result["messages"][0].content.lower()
