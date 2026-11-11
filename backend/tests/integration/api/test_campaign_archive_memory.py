from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import select

from app.ai.providers.schemas import ToolCall
from app.ai.router import ModelConfig
from app.memory.job_worker import run_memory_pass
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.save import Save
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation
from app.schemas.campaign_export import CampaignExport
from tests.integration.api.archive_integrity_checks import assert_archive_rejects_corruption
from tests.integration.gameplay.test_memory_pipeline_cutover import PipelineProvider
from tests.integration.gameplay.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)

pytestmark = pytest.mark.usefixtures("configured_generation")


async def test_archive_exports_the_real_graph_operation_ledger(
    auth_client, db_session, generation_clients
) -> None:
    campaign = await _create_campaign(auth_client, "Archive operation ledger")
    provider = await _openai_provider(auth_client, generation_clients)
    quest_change = ToolCall(
        id="complete-quest",
        name="update_quest",
        arguments={"quest_id": "who_am_i", "status": "completed"},
    )
    _script(
        provider, [_reply("", quest_change), _reply("The quest is complete."), _reply("Dawn.")]
    )

    turn_result = await _take_turn(auth_client, campaign["id"])
    turn_id = UUID(turn_result["turn_id"])
    stored = list(
        await db_session.scalars(
            select(TurnOperation)
            .where(TurnOperation.turn_id == turn_id)
            .order_by(TurnOperation.ordinal)
        )
    )
    assert any(row.payload.name == "update_quest" for row in stored)
    response = await auth_client.get(f"/api/export/{campaign['id']}")
    assert response.status_code == 200, response.text
    archive = response.json()
    exported = [row for row in archive["turn_operations"] if row["turn_id"] == str(turn_id)]
    assert len(exported) == len(stored)
    assert {row["id"] for row in exported} == {str(row.id) for row in stored}
    assert {row["ordinal"] for row in exported} == {row.ordinal for row in stored}
    assert {row["id"]: row["payload"] for row in exported} == {
        str(row.id): row.payload.model_dump(mode="json") for row in stored
    }


class RichPipelineProvider(PipelineProvider):
    def __init__(self, check: Callable[[], None]) -> None:
        super().__init__(check)
        self.global_calls = 0

    async def generate(self, system_prompt, messages, **kwargs):
        self.check()
        self.memory_prompts.append(system_prompt)
        if '"resolved_threads"' in system_prompt:
            self.global_calls += 1
            return (
                '{"story_so_far":"Courier history checkpoint '
                f'{self.global_calls}.","open_threads":["A sealed letter"],'
                '"relationships":["The courier trusts the party."],'
                '"resolved_threads":[]} '
            )
        if '"facts"' in system_prompt:
            return (
                '{"facts":[{"content":"The courier delivered a sealed letter.",'
                '"category":"event","assertion_type":"occurrence",'
                '"entities":[{"name":"The courier","type":"npc","role":"actor"}],'
                '"attribution":[],"source_turns":["t1"],'
                '"temporal_references":["during the watch"],'
                '"importance":{"level":"ordinary",'
                '"reason":"The delivery advances the mystery."}}]}'
            )
        return '{"text":"The courier carries a sealed letter."}'


async def test_archive_exports_complete_records_from_real_memory_pipeline(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    assert_no_db_held: Callable[[], None],
) -> None:
    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    provider = RichPipelineProvider(assert_no_db_held)

    async def resolve(owner):
        return provider, ModelConfig(provider="local", model="archive-controlled", max_tokens=2000)

    monkeypatch.setattr("app.core.dm.dm_nodes.get_user_generation", resolve)
    monkeypatch.setattr("app.memory.job_execution.get_user_generation", resolve)
    created = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Memory archive pipeline",
            "difficulty": "medium",
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = UUID(created.json()["id"])
    head = None
    for number in range(1, 29):
        turn = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={
                "action": f"Wait for the courier, step {number}",
                "request_id": str(UUID(int=number)),
                "expected_head_turn_id": head,
                "expected_context_epoch": 0,
            },
        )
        assert turn.status_code == 200, turn.text
        head = turn.json()["head_turn_id"]
        await run_memory_pass(campaign_id)
    for _ in range(4):
        if provider.global_calls >= 2:
            break
        await run_memory_pass(campaign_id)

    response = await auth_client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200, response.text
    archive = response.json()
    assert len(archive["global_checkpoints"]) >= 2
    first_checkpoint = next(
        row for row in archive["global_checkpoints"] if row["previous_checkpoint_id"] is None
    )
    assert any(
        row["previous_checkpoint_id"] == first_checkpoint["id"]
        for row in archive["global_checkpoints"]
    )
    assert all(checkpoint["generation_id"] for checkpoint in archive["global_checkpoints"])
    assert archive["memory_summaries"] and archive["memory_facts"]
    fact = archive["memory_facts"][0]
    assert fact["batch_id"] and fact["generation_id"] and fact["policy_id"]
    assert fact["category"] == "event" and fact["assertion_type"] == "occurrence"
    assert fact["content"] == "The courier delivered a sealed letter."
    assert fact["fact_metadata"]["entities"][0]["name"] == "The courier"
    assert fact["fact_metadata"]["entities"][0]["role"] == "actor"
    assert fact["fact_metadata"]["attribution"] == []
    assert fact["fact_metadata"]["temporal_references"] == ["during the watch"]
    assert fact["fact_metadata"]["importance"] == {
        "level": "ordinary",
        "reason": "The delivery advances the mystery.",
    }
    source_turn_ids = {
        row["turn_id"] for row in archive["fact_sources"] if row["fact_id"] == fact["id"]
    }
    assert source_turn_ids
    assert source_turn_ids <= {
        row["turn_id"] for row in archive["batch_turns"] if row["batch_id"] == fact["batch_id"]
    }
    assert all(job["state"] == "succeeded" for job in archive["jobs"])
    assert all(attempt["state"] == "succeeded" for attempt in archive["job_attempts"])
    assert all(
        not {"claim_token", "lease_expires_at", "execution_token"} & set(row)
        for row in [*archive["jobs"], *archive["job_attempts"]]
    )

    expected = {
        "turns": (Turn, "id"),
        "turn_operations": (TurnOperation, "id"),
        "continuations": (HistoryContinuation, "id"),
        "saves": (Save, "id"),
        "memory_policies": (MemoryPolicy, "id"),
        "memory_states": (MemoryState, "id"),
        "memory_batches": (MemoryBatch, "id"),
        "batch_turns": (MemoryBatchTurn, None),
        "memory_summaries": (MemorySummary, "id"),
        "global_checkpoints": (MemoryGlobalCheckpoint, "id"),
        "memory_facts": (MemoryFact, "id"),
        "fact_sources": (MemoryFactSource, None),
        "generations": (MemoryGeneration, "id"),
        "jobs": (MemoryJob, "id"),
        "job_attempts": (MemoryJobAttempt, "id"),
    }
    for key, (model, identity) in expected.items():
        rows = list(
            await db_session.scalars(select(model).where(model.campaign_id == campaign_id))
        )
        assert len(archive[key]) == len(rows)
        if identity == "id":
            assert {row["id"] for row in archive[key]} == {str(row.id) for row in rows}
        elif key == "fact_sources":
            assert {(row["fact_id"], row["turn_id"], row["batch_id"]) for row in archive[key]} == {
                (str(row.fact_id), str(row.turn_id), str(row.batch_id)) for row in rows
            }
        elif key == "batch_turns":
            assert {(row["batch_id"], row["turn_id"], row["ordinal"]) for row in archive[key]} == {
                (str(row.batch_id), str(row.turn_id), row.ordinal) for row in rows
            }
    assert provider.global_calls >= 2
    assert_archive_rejects_corruption(CampaignExport.model_validate_json(response.content))
