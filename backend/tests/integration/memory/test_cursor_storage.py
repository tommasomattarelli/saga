import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.memory_document import MemoryState
from tests.integration.memory.storage_support import HistoryFixture


async def test_memory_context_identity_cannot_be_rewritten(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    state = MemoryState(campaign_id=f.campaign.id, policy_id=f.policy.id, context_epoch=0)
    f.session.add(state)
    await f.session.commit()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_states SET context_epoch=1 WHERE id=:id"), {"id": state.id}
        )
        await f.session.commit()
    await f.session.rollback()
