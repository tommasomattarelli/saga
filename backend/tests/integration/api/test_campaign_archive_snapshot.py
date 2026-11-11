import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import Base
from app.models.memory_document import MemorySummary
from app.models.turn import Turn
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)
from tests.integration.memory.test_job_publication import _claimed_job
from tests.integration.memory.test_job_reconciliation import outputs


@pytest.mark.usefixtures("configured_generation")
async def test_archive_keeps_snapshot_when_an_action_commits_between_reads(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import campaign_export

    campaign_id, body = await campaign_and_action(auth_client)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    original = campaign_export._load_rows
    changed = False

    async def read(db, model: type[Base], selected):
        nonlocal changed
        assert await db.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert await db.scalar(text("SHOW transaction_read_only")) == "on"
        if model is Turn and not changed:
            changed = True
            played = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
            assert played.status_code == 200
        return await original(db, model, selected)

    monkeypatch.setattr(campaign_export, "_load_rows", read)
    response = await auth_client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200
    archive = response.json()
    assert changed
    assert archive["campaign"]["active_head_turn_id"] is None
    assert archive["campaign"]["turn_number"] == 0
    assert archive["turns"] == archive["saves"] == []
    current = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert current.json()["turn_number"] == 1


async def test_archive_keeps_prepublication_job_and_document_snapshot(
    auth_client,
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory.job_publication import publish_job
    from app.services import campaign_export

    fixture = history_fixture
    job, claim, generations, batch, _ = await _claimed_job(fixture)
    head = await fixture.session.get(Turn, batch.source_head_turn_id)
    assert head is not None
    fixture.campaign.turn_number = head.turn_number
    await fixture.session.commit()
    original = campaign_export._load_rows
    changed = False

    async def read(db, model: type[Base], selected):
        nonlocal changed
        if model is MemorySummary and not changed:
            changed = True
            assert await publish_job(fixture.session, claim, outputs(generations))
            await fixture.session.commit()
        return await original(db, model, selected)

    monkeypatch.setattr(campaign_export, "_load_rows", read)
    response = await auth_client.get(f"/api/export/{fixture.campaign.id}")
    assert response.status_code == 200, response.text
    archive = response.json()
    assert changed
    assert archive["memory_summaries"] == []
    assert archive["jobs"][0]["id"] == str(job.id)
    assert archive["jobs"][0]["state"] == "running"
    assert archive["memory_states"][0]["last_compacted_batch_id"] is None
    assert archive["memory_batches"][0]["id"] == str(batch.id)
    after = await auth_client.get(f"/api/export/{fixture.campaign.id}")
    assert after.status_code == 200, after.text
    assert len(after.json()["memory_summaries"]) == 1
    assert after.json()["jobs"][0]["state"] == "succeeded"


async def test_exported_json_validates_offline_without_network(
    auth_client,
    tmp_path: Path,
) -> None:
    created = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Offline", "difficulty": "medium"},
    )
    response = await auth_client.get(f"/api/export/{created.json()['id']}")
    assert response.status_code == 200
    path = tmp_path / "campaign.json"
    path.write_bytes(response.content)
    runner = (
        "import runpy, sys; "
        "sys.addaudithook(lambda event, args: (_ for _ in ()).throw(RuntimeError('network forbidden')) "
        "if event in ('socket.connect', 'socket.getaddrinfo') else None); "
        "runpy.run_module('scripts.validate_campaign_export', run_name='__main__')"
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        runner,
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    assert stdout.decode().strip() == "Campaign archive is valid."
