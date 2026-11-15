from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.ai.generation_contracts import RawGenerationReceipt
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationExecutionError,
    GenerationOutcomeStatus,
    GenerationSendKind,
    SendOutcome,
)
from app.memory.generation_ledger import DurableMemoryGenerationLedger
from tests.integration.memory.generation_ledger_support import create_ledger_fixture
from tests.integration.memory.storage_support import HistoryFixture


@pytest.mark.parametrize("fence", ["token", "lease"])
@pytest.mark.parametrize("method", ["reserve", "record", "history"])
async def test_claim_fence_is_rechecked_for_every_ledger_method(
    history_fixture: HistoryFixture, fence: str, method: str
) -> None:
    fixture = await create_ledger_fixture(history_fixture)
    ledger = DurableMemoryGenerationLedger(fixture.claim)
    attempt = GenerationAttempt(
        fixture.request.identity.digest,
        fixture.request.identity.snapshot_json,
        fixture.request.format_mode,
        GenerationSendKind.INITIAL,
    )
    reservation = None
    if method == "record":
        reservation = await ledger.reserve(fixture.identity, "summary", 3, attempt)
    if fence == "token":
        await history_fixture.session.execute(
            text("UPDATE memory_jobs SET claim_token=:token WHERE id=:id"),
            {"token": __import__("uuid").uuid4(), "id": fixture.job_id},
        )
    else:
        await history_fixture.session.execute(
            text("UPDATE memory_jobs SET lease_expires_at=:expiry WHERE id=:id"),
            {
                "expiry": datetime.now(UTC),
                "id": fixture.job_id,
            },
        )
    await history_fixture.session.commit()

    with pytest.raises(GenerationExecutionError):
        if method == "reserve":
            await ledger.reserve(fixture.identity, "summary", 3, attempt)
        elif method == "record":
            assert reservation is not None
            await ledger.record(
                fixture.identity,
                "summary",
                SendOutcome(
                    reservation,
                    GenerationOutcomeStatus.VALID,
                    receipt=RawGenerationReceipt(text='{"value":"late"}'),
                ),
            )
        else:
            await ledger.history(fixture.identity, "summary")
