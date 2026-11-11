from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.turn_request import TurnRequest
from tests.integration.memory.storage_support import HistoryFixture


@pytest.mark.parametrize(
    "case", ["duplicate_running", "missing_result", "changed_payload", "success"]
)
async def test_turn_request_identity_slot_and_committed_result(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    head = await f.turn()
    request = TurnRequest(
        request_id=uuid4(),
        campaign_id=f.campaign.id,
        payload_hash="1" * 64,
        starting_head_turn_id=head.id,
        context_epoch=0,
        state="running",
        execution_token=uuid4(),
        execution_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        claimed_turn_number=2,
    )
    f.session.add(request)
    await f.session.commit()
    if case == "duplicate_running":
        f.session.add(
            TurnRequest(
                request_id=uuid4(),
                campaign_id=f.campaign.id,
                payload_hash="2" * 64,
                starting_head_turn_id=head.id,
                context_epoch=0,
                state="running",
                execution_token=uuid4(),
                execution_expires_at=request.execution_expires_at,
                claimed_turn_number=3,
            )
        )
        with pytest.raises(IntegrityError):
            await f.session.commit()
    elif case == "changed_payload":
        with pytest.raises(IntegrityError):
            await f.session.execute(
                update(TurnRequest)
                .where(TurnRequest.request_id == request.request_id)
                .values(payload_hash="3" * 64)
            )
            await f.session.commit()
    else:
        result = await f.turn(head, number=2)
        request.state = "committed"
        request.execution_token = request.execution_expires_at = None
        request.result_turn_id = result.id if case == "success" else None
        if case == "missing_result":
            with pytest.raises(IntegrityError):
                await f.session.commit()
        else:
            await f.session.commit()
            request_id = request.request_id
            f.session.expunge_all()
            loaded = await f.session.get(TurnRequest, request_id)
            assert (
                loaded is not None
                and loaded.state == "committed"
                and loaded.result_turn_id is not None
            )
    await f.session.rollback()
