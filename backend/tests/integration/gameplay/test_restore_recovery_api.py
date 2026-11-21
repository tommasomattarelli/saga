from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.turn import Turn
from app.models.turn_request import TurnRequest

pytestmark = pytest.mark.usefixtures("configured_generation")


def _result(state: dict) -> dict:
    return {
        **state,
        "narration": "The party records another event.",
        "narration_segments": [],
        "dice_results": [],
        "time_passed_minutes": 0,
        "death_event": None,
        "model_used": "restore-test",
    }


async def _campaign_action(client) -> tuple[str, dict]:
    response = await client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Restore ancestry",
            "difficulty": "medium",
        },
    )
    assert response.status_code == 201, response.text
    campaign = response.json()
    return campaign["id"], {
        "action": "Record the next event",
        "request_id": str(uuid4()),
        "expected_head_turn_id": campaign.get("active_head_turn_id"),
        "expected_context_epoch": campaign.get("context_epoch", 0),
    }


async def _act(client, campaign_id: str, body: dict, head: str | None, epoch: int) -> dict:
    request = {
        **body,
        "request_id": str(uuid4()),
        "expected_head_turn_id": head,
        "expected_context_epoch": epoch,
    }
    response = await client.post(f"/api/campaigns/{campaign_id}/action", json=request)
    assert response.status_code == 200, response.text
    return response.json()


async def _save(client, campaign_id: str, name: str) -> str:
    response = await client.post(f"/api/saves/{campaign_id}", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_repeated_api_loads_keep_equal_turn_number_futures_on_distinct_ancestries(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def generate(state: dict, **_: object) -> dict:
        return _result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    campaign_id, body = await _campaign_action(auth_client)

    root = await _act(auth_client, campaign_id, body, None, 0)
    first_save = await _save(auth_client, campaign_id, "Shared prefix")
    first_branch_head = await _act(auth_client, campaign_id, body, root["head_turn_id"], 0)
    first_future_save = await _save(auth_client, campaign_id, "First future")

    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{first_save}")
    assert loaded.status_code == 200, loaded.text
    second_branch_head = await _act(
        auth_client,
        campaign_id,
        body,
        loaded.json()["active_head_turn_id"],
        loaded.json()["context_epoch"],
    )
    second_save = await _save(auth_client, campaign_id, "Second future")
    assert first_branch_head["turn_number"] == second_branch_head["turn_number"]
    assert first_branch_head["turn_id"] != second_branch_head["turn_id"]

    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{first_save}")
    assert loaded.status_code == 200, loaded.text
    third_branch_head = await _act(
        auth_client,
        campaign_id,
        body,
        loaded.json()["active_head_turn_id"],
        loaded.json()["context_epoch"],
    )
    assert third_branch_head["turn_number"] == second_branch_head["turn_number"]
    assert third_branch_head["turn_id"] not in {
        first_branch_head["turn_id"],
        second_branch_head["turn_id"],
    }
    third_save = await _save(auth_client, campaign_id, "Third future")

    for save_id, expected_head in (
        (first_future_save, first_branch_head["turn_id"]),
        (second_save, second_branch_head["turn_id"]),
        (third_save, third_branch_head["turn_id"]),
    ):
        restored = await auth_client.post(f"/api/saves/{campaign_id}/load/{save_id}")
        assert restored.status_code == 200
        assert restored.json()["active_head_turn_id"] == expected_head
        history = await auth_client.get(f"/api/journal/{campaign_id}")
        assert {row["turn_id"] for row in history.json()} == {root["turn_id"], expected_head}

    journal = await auth_client.get(f"/api/journal/{campaign_id}")
    assert journal.status_code == 200
    active_ids = {row["turn_id"] for row in journal.json()}
    assert active_ids == {root["turn_id"], third_branch_head["turn_id"]}
    assert first_branch_head["turn_id"] not in active_ids
    assert second_branch_head["turn_id"] not in active_ids

    saves = await auth_client.get(f"/api/saves/{campaign_id}")
    assert saves.status_code == 200
    assert {item["id"] for item in saves.json()} >= {
        first_save,
        first_future_save,
        second_save,
    }
    campaign = await db_session.get(Campaign, UUID(campaign_id), populate_existing=True)
    assert campaign is not None
    assert campaign.active_head_turn_id == UUID(third_branch_head["head_turn_id"])
    active_head = await db_session.get(Turn, campaign.active_head_turn_id)
    assert active_head is not None
    assert active_head.parent_turn_id == UUID(root["turn_id"])
    assert active_head.turn_number == second_branch_head["turn_number"]
    request = await db_session.scalar(
        select(TurnRequest).where(TurnRequest.request_id == UUID(third_branch_head["request_id"]))
    )
    assert request is not None and request.state == "committed"
