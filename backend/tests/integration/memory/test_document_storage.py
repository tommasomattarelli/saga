import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.memory.document_contracts import FactEntity, FactImportance, FactMetadata, GlobalPayload
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from tests.integration.memory.document_support import generation, summary
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


def fact_metadata(*, level: str = "ordinary") -> FactMetadata:
    return FactMetadata(
        entities=(FactEntity(name="Mira", type="npc", role="speaker"),),
        attribution=(0,),
        temporal_references=(),
        importance=FactImportance(level=level, reason="A clue was revealed."),
    )


def global_payload() -> GlobalPayload:
    return GlobalPayload(
        story_so_far="The party found the gate.",
        open_threads=("Find the key.",),
        relationships=(),
        resolved_threads=(),
    )


async def test_typed_documents_and_fact_sources_survive_round_trip(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    document = await summary(f, item)
    fact = MemoryFact(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=item.id,
        ordinal=1,
        schema_version=1,
        content="Mira said the key opens the gate.",
        category="information",
        assertion_type="statement",
        fact_metadata=fact_metadata(),
        generation_id=document.generation_id,
    )
    f.session.add_all(
        [
            fact,
            MemoryFactSource(
                fact_id=fact.id, batch_id=item.id, campaign_id=f.campaign.id, turn_id=first.id
            ),
        ]
    )
    await f.session.commit()
    fact_id, document_id = fact.id, document.id
    f.session.expunge_all()
    loaded = await f.session.get(MemoryFact, fact_id)
    assert loaded is not None and loaded.fact_metadata == fact_metadata()
    assert loaded.turn_number is None and loaded.entity_name is None
    saved_summary = await f.session.get(MemorySummary, document_id)
    assert saved_summary is not None and saved_summary.payload.text == "The party found a clue."


@pytest.mark.parametrize(
    "case", ["missing_source", "outside_batch", "unknown_importance", "unattributed_statement"]
)
async def test_facts_require_real_sources_and_policy_metadata(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    outside = await f.turn(second)
    item = await batch(f, [first, second])
    produced = await generation(f, item)
    metadata = fact_metadata(level="invented" if case == "unknown_importance" else "ordinary")
    if case == "unattributed_statement":
        metadata = metadata.model_copy(update={"attribution": ()})
    fact = MemoryFact(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=item.id,
        ordinal=1,
        schema_version=1,
        content="Mira declared a deadline.",
        category="commitment",
        assertion_type="statement",
        fact_metadata=metadata,
        generation_id=produced.id,
    )
    f.session.add(fact)
    if case != "missing_source":
        f.session.add(
            MemoryFactSource(
                fact_id=fact.id,
                batch_id=item.id,
                campaign_id=f.campaign.id,
                turn_id=outside.id if case == "outside_batch" else first.id,
            )
        )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_checkpoint_transition_and_coverage_are_explicit(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns = []
    for number in (1, 4, 4, 8, 9, 12):
        turns.append(await f.turn(turns[-1] if turns else None, number=number))
    first = await batch(f, turns[:2])
    second = await batch(f, turns[2:4], first)
    await summary(f, first)
    await summary(f, second)
    produced = await generation(f, first, role="global")
    checkpoint = MemoryGlobalCheckpoint(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=first.id,
        payload=global_payload(),
        generation_id=produced.id,
    )
    state = MemoryState(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        context_epoch=0,
        global_checkpoint_id=checkpoint.id,
        last_compacted_batch_id=second.id,
    )
    f.session.add_all([checkpoint, state])
    f.campaign.active_head_turn_id = turns[-1].id
    f.campaign.active_memory_state_id = state.id
    await f.session.commit()
    state_id, head_id = state.id, turns[2].id
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE campaigns SET active_head_turn_id=:head WHERE id=:campaign"),
            {"head": head_id, "campaign": f.campaign.id},
        )
        await f.session.commit()
    await f.session.rollback()
    restored = await f.session.get(MemoryState, state_id)
    assert restored is not None and restored.global_checkpoint_id is not None


async def test_checkpoint_cannot_skip_first_batch(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    turns = []
    for _ in range(4):
        turns.append(await f.turn(turns[-1] if turns else None))
    first = await batch(f, turns[:2])
    second = await batch(f, turns[2:], first)
    with pytest.raises(IntegrityError):
        produced = await generation(f, second, role="global")
        f.session.add(
            MemoryGlobalCheckpoint(
                campaign_id=f.campaign.id,
                policy_id=f.policy.id,
                batch_id=second.id,
                payload=global_payload(),
                generation_id=produced.id,
            )
        )
        await f.session.commit()
    await f.session.rollback()


async def test_summary_is_not_duplicated_or_overwritten(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    document = await summary(f, item)
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_summaries SET payload='{}'::jsonb WHERE id=:id"),
            {"id": document.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_cursors_cannot_expose_an_unpublished_batch(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    f.session.add(
        MemoryState(
            campaign_id=f.campaign.id,
            policy_id=f.policy.id,
            context_epoch=0,
            last_compacted_batch_id=item.id,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_global_transition_is_unique_even_without_a_predecessor(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    produced = await generation(f, item, role="global")
    f.session.add_all(
        [
            MemoryGlobalCheckpoint(
                campaign_id=f.campaign.id,
                policy_id=f.policy.id,
                batch_id=item.id,
                payload=global_payload(),
                generation_id=produced.id,
            ),
            MemoryGlobalCheckpoint(
                campaign_id=f.campaign.id,
                policy_id=f.policy.id,
                batch_id=item.id,
                payload=global_payload(),
                generation_id=produced.id,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_sql_fact_cannot_omit_required_attribution(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    produced = await generation(f, item)
    metadata = fact_metadata().model_dump(mode="json")
    del metadata["attribution"]
    fact_id = uuid4()
    await f.session.execute(
        text(
            "INSERT INTO memory_facts (id,campaign_id,batch_id,policy_id,ordinal,content,category,"
            "assertion_type,fact_metadata,generation_id,schema_version) VALUES "
            "(:id,:campaign,:batch,:policy,1,'Mira promised to help.','commitment','statement',"
            "CAST(:metadata AS jsonb),:generation,1)"
        ),
        {
            "id": fact_id,
            "campaign": f.campaign.id,
            "batch": item.id,
            "policy": f.policy.id,
            "metadata": json.dumps(metadata),
            "generation": produced.id,
        },
    )
    f.session.add(
        MemoryFactSource(
            fact_id=fact_id, batch_id=item.id, campaign_id=f.campaign.id, turn_id=first.id
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_full_campaign_deletion_removes_documents_atomically(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    await summary(f, item)
    campaign_id = f.campaign.id
    await f.session.delete(f.campaign)
    await f.session.commit()
    assert (
        await f.session.scalar(
            text("SELECT count(*) FROM memory_summaries WHERE campaign_id=:id"),
            {"id": campaign_id},
        )
        == 0
    )
