from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_execute_job_scopes_internal_execution_to_campaign(mocker):
    from app.ai.session_affinity import _campaign
    from app.memory import job_execution

    campaign_id, job_id = uuid4(), uuid4()
    internal = mocker.patch.object(
        job_execution,
        "_execute_job",
        mocker.AsyncMock(side_effect=lambda campaign, job: _campaign.get() == campaign),
    )

    assert await job_execution.execute_job(campaign_id, job_id)
    internal.assert_awaited_once_with(campaign_id, job_id)
    assert _campaign.get() is None
