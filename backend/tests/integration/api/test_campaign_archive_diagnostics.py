import pytest

from app.models.memory_job import MemoryJobAttempt
from app.models.turn import Turn
from app.services.campaign_export import build_campaign_export
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)
from tests.integration.memory.test_job_publication import _claimed_job


@pytest.mark.parametrize(
    "error",
    [
        "Traceback /private/server.py RuntimeError Bearer sk-private-secret",
        "Memory generation requires a configuration update.",
    ],
)
async def test_archive_diagnostics_allowlist_errors_and_exclude_runtime_claims(
    auth_client,
    history_fixture: HistoryFixture,
    error: str,
) -> None:
    fixture = history_fixture
    job, claim, _, batch, _ = await _claimed_job(fixture)
    head = await fixture.session.get(Turn, batch.source_head_turn_id)
    assert head is not None
    fixture.campaign.turn_number = head.turn_number
    job.last_error = error
    attempt = await fixture.session.get(MemoryJobAttempt, claim.attempt_id)
    assert attempt is not None
    attempt.error = error
    await fixture.session.commit()
    await build_campaign_export(fixture.campaign.id, fixture.campaign.user_id)
    response = await auth_client.get(f"/api/export/{fixture.campaign.id}")
    assert response.status_code == 200, response.text
    archive = response.json()
    exported_job = archive["jobs"][0]
    exported_attempt = archive["job_attempts"][0]
    forbidden = {
        "claim_token",
        "lease_expires_at",
        "next_attempt_at",
        "instruction_text",
        "manifest",
        "logical_key",
    }
    assert forbidden.isdisjoint(exported_job)
    assert forbidden.isdisjoint(exported_attempt)
    assert str(claim.token) not in response.text
    assert "active_action_request_id" not in archive["campaign"]
    if error.startswith("Traceback"):
        assert "sk-private-secret" not in response.text
        assert (
            exported_job["last_error"]
            == exported_attempt["error"]
            == "Memory generation did not complete successfully."
        )
    else:
        assert exported_job["last_error"] == exported_attempt["error"] == error
