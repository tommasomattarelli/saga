from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.memory_fact import MemoryFact
from app.models.turn import Turn
from app.schemas.campaign_export import CampaignExport
from app.services.export_validation import ExportIntegrityError, validate_campaign_export
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result


async def test_export_versioned_empty_campaign_has_complete_collections(auth_client) -> None:
    created = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Archive", "difficulty": "medium"},
    )
    response = await auth_client.get(f"/api/export/{created.json()['id']}")
    assert response.status_code == 200
    archive = response.json()
    assert archive["format_version"] == 1
    assert archive["campaign"]["id"] == created.json()["id"]
    assert len(archive["continuations"]) == len(archive["memory_policies"]) == 1
    assert len(archive["memory_states"]) == 1
    for key in (
        "turns",
        "turn_operations",
        "saves",
        "memory_batches",
        "batch_turns",
        "memory_summaries",
        "global_checkpoints",
        "memory_facts",
        "fact_sources",
        "generations",
        "jobs",
        "job_attempts",
    ):
        assert archive[key] == []


@pytest.mark.usefixtures("configured_generation")
async def test_export_preserves_branches_saves_and_recorded_operations(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    prefix = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert prefix.status_code == 200
    beginning = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Shared prefix"})
    next_body = {
        **body,
        "request_id": str(uuid4()),
        "expected_head_turn_id": prefix.json()["turn_id"],
    }
    first = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=next_body)
    assert first.status_code == 200
    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{beginning.json()['id']}")
    assert loaded.status_code == 200
    second = await auth_client.post(
        f"/api/campaigns/{campaign_id}/action",
        json={**next_body, "request_id": str(uuid4()), "expected_context_epoch": 1},
    )
    assert second.status_code == 200
    response = await auth_client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200
    archive = response.json()
    turns = archive["turns"]
    assert {turn["id"] for turn in turns} == {
        prefix.json()["turn_id"],
        first.json()["turn_id"],
        second.json()["turn_id"],
    }
    futures = [turn for turn in turns if turn["id"] != prefix.json()["turn_id"]]
    assert {turn["turn_number"] for turn in futures} == {2}
    assert {turn["parent_turn_id"] for turn in futures} == {prefix.json()["turn_id"]}
    assert len({turn["continuation_id"] for turn in turns}) == 2
    assert archive["campaign"]["active_head_turn_id"] == second.json()["turn_id"]
    assert len(archive["saves"]) == 4
    assert all(turn["operations_version"] == 1 and turn["operation_count"] == 0 for turn in turns)
    assert archive["turn_operations"] == []
    assert all("campaign_snapshot" in save for save in archive["saves"])
    parsed = CampaignExport.model_validate_json(response.content)
    wrong_branch = parsed.model_copy(deep=True)
    wrong_branch.campaign.active_head_turn_id = UUID(first.json()["turn_id"])
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_branch)
    wrong_save = parsed.model_copy(deep=True)
    active_save = next(
        save for save in wrong_save.saves if save.head_turn_id == UUID(second.json()["turn_id"])
    )
    active_save.head_turn_id = UUID(first.json()["turn_id"])
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_save)


async def test_export_preserves_legacy_sources_without_inventing_history(
    auth_client,
    db_session,
) -> None:
    created = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Legacy", "difficulty": "medium"},
    )
    campaign_id = UUID(created.json()["id"])
    campaign = await db_session.scalar(select(Campaign).where(Campaign.id == campaign_id))
    assert campaign is not None
    campaign.memory_policy_id = None
    campaign.active_memory_state_id = None
    campaign.active_continuation_id = None
    campaign.global_summary = "An old consolidated account."
    db_session.add_all(
        [
            Turn(
                campaign_id=campaign_id,
                turn_number=4,
                player_action="Listen",
                narration="",
                model_used="old",
            ),
            MemoryFact(
                campaign_id=campaign_id,
                turn_number=4,
                entity_name="Mira",
                entity_type="npc",
                content="Mira spoke.",
            ),
            MemoryFact(
                campaign_id=campaign_id,
                turn_number=4,
                entity_name="Mira",
                entity_type="npc",
                content="Mira promised to return.",
            ),
        ]
    )
    await db_session.commit()
    response = await auth_client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200
    archive = response.json()
    assert archive["campaign"]["memory_policy_id"] is None
    assert archive["campaign"]["global_summary"] == "An old consolidated account."
    assert archive["turns"][0]["narration"] == ""
    assert archive["turns"][0]["operations_version"] is None
    assert archive["turns"][0]["continuation_id"] is None
    assert archive["memory_facts"][0]["batch_id"] is None
    assert len(archive["memory_facts"]) == 2
    assert archive["fact_sources"] == []
