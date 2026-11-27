from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_fact import MemoryFact
from tests.integration.memory.storage_support import HistoryFixture


async def _matches(session: AsyncSession, term: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(MemoryFact)
            .where(MemoryFact.search_vector.op("@@")(func.to_tsquery("simple", term)))
        )
        or 0
    )


async def test_search_vector_tracks_content(history_fixture: HistoryFixture) -> None:
    fact = MemoryFact(
        id=uuid4(),
        campaign_id=history_fixture.campaign.id,
        turn_number=1,
        entity_name="Witness",
        entity_type="npc",
        content="Lyra promised the silver key at Thornhaven.",
    )
    history_fixture.session.add(fact)
    await history_fixture.session.commit()

    assert await _matches(history_fixture.session, "Lyra") == 1
    assert await _matches(history_fixture.session, "Thornhaven") == 1

    fact.content = "Aldric hid the map in the shrine."
    await history_fixture.session.commit()

    assert await _matches(history_fixture.session, "Lyra") == 0
    assert await _matches(history_fixture.session, "Aldric") == 1
