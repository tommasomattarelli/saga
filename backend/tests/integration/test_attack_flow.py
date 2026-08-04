"""The attack pipeline over a real campaign and a real DB (ADR 0003 S2b, §G).

Combat is no longer a mode: there is nothing to open, so every one of these runs
straight off a freshly created campaign.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.core.dice import DiceOutcome, resolve_check
from app.core.dm.dm_tools_executor import tools_node
from app.models.campaign import Campaign


async def _create_campaign(auth_client) -> str:
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Attack Campaign",
            "death_mode": "destino",
            "character_data": {
                "name": "Eron",
                "hp": {"current": 40, "max": 40},
                "abilities": {"strength": 16, "dexterity": 12},
            },
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _load(db_session, campaign_id: str) -> Campaign:
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    return result.scalar_one()


def _state(campaign: Campaign, *tool_calls: dict) -> dict:
    return {
        "messages": [AIMessage(content="", tool_calls=list(tool_calls))],
        "world_state": campaign.world_state,
        "char_data": campaign.character_data,
        "player_action": "",
        "campaign_id": str(campaign.id),
        "narration": "Steel rings.",
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


def _call(name: str, tc_id: str = "tc1", **args) -> dict:
    return {"id": tc_id, "name": name, "args": args, "type": "tool_call"}


def _hit(tier: DiceOutcome = DiceOutcome.FULL_SUCCESS):
    def fixed(modifier, difficulty, advantage=False, disadvantage=False):
        resolution = resolve_check(modifier, difficulty, advantage, disadvantage)
        resolution.outcome = tier
        return resolution

    return patch("app.core.attack.resolve_check", side_effect=fixed)


@pytest.mark.asyncio
async def test_a_brand_new_enemy_is_born_a_record_and_takes_the_hit(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))
    before = len(campaign.world_state["npcs"])

    with _hit():
        result = await tools_node(
            _state(
                campaign, _call("attack", attacker="Eron", target="Goblin", weapon_class="medium")
            )
        )

    npcs = result["world_state"]["npcs"]
    assert len(npcs) == before + 1
    goblin = next(n for n in npcs.values() if n["name"] == "Goblin")
    assert goblin["auto_created"] is True
    assert goblin["location"] == campaign.world_state["meta"]["current_location"]
    assert goblin["hp"] < goblin["max_hp"]
    assert "damage" in result["tool_events"][0]["extra"]


@pytest.mark.asyncio
async def test_an_authored_npc_can_be_struck_and_dies_on_its_record(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))
    marta_id = next(k for k, v in campaign.world_state["npcs"].items() if v["name"] == "Marta")
    campaign.world_state["npcs"][marta_id]["hp"] = 1

    with _hit():
        result = await tools_node(
            _state(
                campaign, _call("attack", attacker="Eron", target="Marta", weapon_class="heavy")
            )
        )

    marta = result["world_state"]["npcs"][marta_id]
    assert marta["hp"] == 0
    assert marta["lifecycle"] == "dead"  # the 0009 writer, now off the record


@pytest.mark.asyncio
async def test_an_npc_strikes_back_at_the_player_in_the_same_step(auth_client, db_session):
    """The exchange convention (C1c) — two calls, one turn, no rounds."""
    campaign = await _load(db_session, await _create_campaign(auth_client))

    with _hit():
        result = await tools_node(
            _state(
                campaign,
                _call("attack", "tc1", attacker="Eron", target="Bandit", weapon_class="medium"),
                _call("attack", "tc2", attacker="Bandit", target="Eron"),
            )
        )

    bandit = next(n for n in result["world_state"]["npcs"].values() if n["name"] == "Bandit")
    assert bandit["hp"] < bandit["max_hp"]
    assert result["char_data"]["hp"]["current"] < 40
    assert len(result["tool_events"]) == 2


@pytest.mark.asyncio
async def test_a_typo_never_spawns_a_phantom_enemy(auth_client, db_session):
    campaign = await _load(db_session, await _create_campaign(auth_client))
    before = len(campaign.world_state["npcs"])

    result = await tools_node(
        _state(campaign, _call("attack", attacker="Eron", target="Martaa", weapon_class="light"))
    )

    assert len(result["world_state"]["npcs"]) == before
    assert "Marta" in result["messages"][0].content


@pytest.mark.asyncio
async def test_the_removed_combat_tools_are_gone(auth_client, db_session):
    """ADR 0003 §G — the removed-tools set stays removed."""
    campaign = await _load(db_session, await _create_campaign(auth_client))

    for tool in ("start_combat", "end_combat", "apply_damage", "update_hp"):
        result = await tools_node(_state(campaign, _call(tool, enemies=[], amount=99, change=99)))
        assert "unknown tool" in result["messages"][0].content.lower()

    assert "combat_state" not in campaign.world_state
