import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.memory_generation import MemoryGeneration
from tests.integration.memory.job_support import job_sources, new_attempt, new_generation, new_job
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


@pytest.mark.parametrize("case", ["mixed_attempt", "mixed_batch", "rewrite_provenance"])
async def test_generation_provenance_must_match_the_same_job(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    turns, first_batch, state = await job_sources(f)
    third = await f.turn(turns[-1])
    fourth = await f.turn(third)
    second_batch = await batch(f, [third, fourth], first_batch)
    first_job = new_job(f, turns, first_batch, state)
    second_job = new_job(f, [third, fourth], second_batch, state, key="9" * 64)
    first_attempt, second_attempt = new_attempt(first_job, 1), new_attempt(second_job, 1)
    f.session.add_all([first_job, second_job, first_attempt, second_attempt])
    await f.session.commit()
    produced = new_generation(first_job, first_attempt)
    f.session.add(produced)
    await f.session.commit()
    if case == "rewrite_provenance":
        with pytest.raises(IntegrityError):
            await f.session.execute(
                update(MemoryGeneration)
                .where(MemoryGeneration.id == produced.id)
                .values(provider="rewritten")
            )
            await f.session.commit()
    else:
        invalid = new_generation(first_job, first_attempt)
        if case == "mixed_attempt":
            invalid.attempt_id = second_attempt.id
        else:
            invalid.batch_id = second_batch.id
        f.session.add(invalid)
        with pytest.raises(IntegrityError):
            await f.session.commit()
    await f.session.rollback()
