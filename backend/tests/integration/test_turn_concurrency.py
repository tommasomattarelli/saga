"""A-3: concurrent player actions must not collide on turn_number.

The endpoint claims the next turn number with an atomic ``UPDATE ... RETURNING``
inside a short session that closes before the graph runs, so two in-flight turns
on the same campaign get distinct, sequential numbers and produce distinct rows.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.turn import Turn


def _fake_state() -> dict:
    return {
        "world_state": {"meta": {"current_location": "Town"}},
        "char_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        "narration": "The dust settles.",
        "narration_segments": None,
        "dice_results": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "npc_dialogues": [],
        "death_event": None,
        "model_used": "test-model",
        "importance_score": 5,
        "time_passed_minutes": 0,
    }


async def _create_campaign(auth_client) -> str:
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Concurrency Campaign",
            "death_mode": "destino",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_concurrent_actions_get_distinct_sequential_turn_numbers(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    n = 5

    with (
        patch(
            "app.api.turns.dm_graph.ainvoke",
            new=AsyncMock(side_effect=lambda *a, **k: _fake_state()),
        ),
        patch("app.api.turns.compress_turn_to_summary", new=AsyncMock(return_value="summary")),
        patch("app.api.turns.generate_embedding", new=AsyncMock(return_value=[0.0] * 384)),
        patch("app.api.turns.extract_and_store_facts", new=AsyncMock(return_value=None)),
        patch("app.api.turns._background_compression", new=AsyncMock(return_value=None)),
        patch("app.api.turns._background_global_summary", new=AsyncMock(return_value=None)),
    ):
        responses = await asyncio.gather(
            *(
                auth_client.post(
                    f"/api/campaigns/{campaign_id}/action",
                    json={"action": f"action {i}"},
                )
                for i in range(n)
            )
        )

    assert all(r.status_code == 200 for r in responses)

    turn_numbers = sorted(r.json()["turn_number"] for r in responses)
    # Distinct and a contiguous 1..n sequence (campaign starts at turn 0).
    assert turn_numbers == list(range(1, n + 1))

    count = await db_session.scalar(
        select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
    )
    assert count == n

    persisted = await db_session.scalars(
        select(Turn.turn_number).where(Turn.campaign_id == campaign_id)
    )
    assert sorted(persisted.all()) == list(range(1, n + 1))
