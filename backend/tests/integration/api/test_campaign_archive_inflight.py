import asyncio
from uuid import uuid4

import pytest

from app.exceptions import AIProviderError
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result

pytestmark = pytest.mark.usefixtures("configured_generation")


async def test_archive_and_save_remain_valid_during_first_action_after_restore(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    prefix = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert prefix.status_code == 200
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Shared prefix"})
    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200
    entered, release = asyncio.Event(), asyncio.Event()

    async def suspended(state, **kwargs):
        entered.set()
        await release.wait()
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", suspended)
    submission = {
        **body,
        "request_id": str(uuid4()),
        "expected_head_turn_id": prefix.json()["turn_id"],
        "expected_context_epoch": 1,
    }
    running = asyncio.create_task(
        auth_client.post(f"/api/campaigns/{campaign_id}/action", json=submission)
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        pending_save = await auth_client.post(
            f"/api/saves/{campaign_id}", json={"name": "During action"}
        )
        assert pending_save.status_code == 201
        response = await auth_client.get(f"/api/export/{campaign_id}")
        assert response.status_code == 200, response.text
        archive = response.json()
        assert archive["campaign"]["turn_number"] == 2
        assert archive["campaign"]["active_head_turn_id"] == prefix.json()["turn_id"]
        assert len(archive["turns"]) == 1
        assert len(archive["continuations"]) == 2
        pending = next(
            save for save in archive["saves"] if save["id"] == pending_save.json()["id"]
        )
        assert pending["head_turn_id"] == prefix.json()["turn_id"] and pending["turn_number"] == 2
    finally:
        release.set()
        completed = await running
        assert completed.status_code == 200, completed.text


async def test_archive_preserves_empty_continuations_and_claimed_number_gaps(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    prefix = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Shared prefix"})
    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200

    async def fail(state, **kwargs):
        raise AIProviderError("controlled", "Controlled generation failure")

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", fail)
    submission = {
        **body,
        "request_id": str(uuid4()),
        "expected_head_turn_id": prefix.json()["turn_id"],
        "expected_context_epoch": 1,
    }
    failed = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=submission)
    assert failed.status_code == 502
    empty_save = await auth_client.post(
        f"/api/saves/{campaign_id}", json={"name": "After interruption"}
    )
    assert empty_save.status_code == 201
    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{empty_save.json()['id']}")
    assert loaded.status_code == 200
    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    played = await auth_client.post(
        f"/api/campaigns/{campaign_id}/action",
        json={**submission, "request_id": str(uuid4()), "expected_context_epoch": 2},
    )
    assert played.status_code == 200, played.text
    response = await auth_client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200, response.text
    archive = response.json()
    assert len(archive["continuations"]) == 3
    assert {turn["turn_number"] for turn in archive["turns"]} == {1, 3}
