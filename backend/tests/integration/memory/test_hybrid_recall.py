import uuid
from collections.abc import Mapping

from sqlalchemy import select

from app.memory.history import history_path
from app.memory.job_publication import publish_job
from app.memory.semantic import HybridHit, search_hybrid_facts
from app.models.embedding_index import EmbeddingIndex
from app.models.memory_fact import MemoryFact
from app.models.turn import Turn
from tests.integration.memory.job_support import outputs_for
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_history_recall import (
    _claimed_job,
    _embed_fact,
    _fact_payload,
    _index,
    _publish_alternate_batch,
)


async def _ancestry(fixture: HistoryFixture) -> tuple[uuid.UUID, ...]:
    return tuple(
        turn.id
        for turn in await history_path(
            fixture.session, fixture.campaign.id, fixture.campaign.active_head_turn_id
        )
    )


async def _hybrid(
    fixture: HistoryFixture,
    vectors: Mapping[str, tuple[float, ...]],
    lexical_query: str,
    *,
    use_action: bool = True,
    use_anchor: bool = True,
    use_lexical: bool = True,
) -> list[HybridHit]:
    index = await fixture.session.scalar(
        select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == fixture.campaign.id)
    )
    assert index is not None
    return await search_hybrid_facts(
        fixture.session,
        campaign_id=fixture.campaign.id,
        index_id=index.id,
        dimension=384,
        pool=25,
        rrf_k=60,
        ancestry_turn_ids=await _ancestry(fixture),
        vectors=vectors,
        lexical_query=lexical_query,
        use_action=use_action,
        use_anchor=use_anchor,
        use_lexical=use_lexical,
    )


async def test_hybrid_fuses_dense_and_lexical_ranks(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    fixture.session.add(_index(fixture))
    await fixture.session.commit()
    _job, claim, generations, batch, _state = await _claimed_job(
        fixture,
        raw_by_role={
            "summary": '{"text":"Lexical summary."}',
            "facts": _fact_payload("Lyra kept the silver key."),
        },
    )
    assert await publish_job(fixture.session, claim, outputs_for(generations))
    await fixture.session.commit()
    fact = await fixture.session.scalar(select(MemoryFact).where(MemoryFact.batch_id == batch.id))
    assert fact is not None
    await _embed_fact(fixture, fact, [1.0] + [0.0] * 383)

    hits = await _hybrid(
        fixture,
        vectors={"action": (1.0,) + (0.0,) * 383, "anchor": (0.0,) * 384},
        lexical_query="lyra",
        use_anchor=False,
    )

    assert [hit.fact_id for hit in hits] == [fact.id]
    assert hits[0].score > 1 / 61  # the same fact contributes to both dense and lexical ranks


async def test_lexical_only_search_needs_no_embedding_index(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    _job, claim, generations, _batch, _state = await _claimed_job(
        fixture,
        raw_by_role={
            "summary": '{"text":"No index summary."}',
            "facts": _fact_payload("Lyra kept the silver key."),
        },
    )
    assert await publish_job(fixture.session, claim, outputs_for(generations))
    await fixture.session.commit()
    fact = await fixture.session.scalar(
        select(MemoryFact).where(MemoryFact.content == "Lyra kept the silver key.")
    )
    assert fact is not None

    hits = await search_hybrid_facts(
        fixture.session,
        campaign_id=fixture.campaign.id,
        index_id=None,
        dimension=None,
        vectors={},
        lexical_query="lyra",
        ancestry_turn_ids=await _ancestry(fixture),
        pool=25,
        rrf_k=60,
        use_action=False,
        use_anchor=False,
    )

    assert [hit.fact_id for hit in hits] == [fact.id]


async def test_future_batch_is_excluded_from_dense_and_lexical_branches(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    fixture.session.add(_index(fixture))
    await fixture.session.commit()
    _job, claim, generations, crossing_batch, _state = await _claimed_job(
        fixture,
        raw_by_role={
            "summary": '{"text":"Future summary."}',
            "facts": _fact_payload("Lyra future secret."),
        },
    )
    assert await publish_job(fixture.session, claim, outputs_for(generations))
    await fixture.session.commit()
    crossing_fact = await fixture.session.scalar(
        select(MemoryFact).where(MemoryFact.batch_id == crossing_batch.id)
    )
    assert crossing_fact is not None
    await _embed_fact(fixture, crossing_fact, [1.0] + [0.0] * 383)

    first = await fixture.session.get(Turn, claim.manifest.source_turn_ids[0])
    assert first is not None
    fork = await fixture.fork(first)
    branch_turn = await fixture.turn(first, continuation=fork, number=3)
    fixture.campaign.active_continuation_id = fork.id
    fixture.campaign.active_head_turn_id = branch_turn.id
    await fixture.session.commit()
    _active_batch, active_fact = await _publish_alternate_batch(
        fixture, (first, branch_turn), "Aldric active clue."
    )
    await _embed_fact(fixture, active_fact, [0.0, 1.0] + [0.0] * 382)

    hits = await _hybrid(
        fixture,
        vectors={"action": (1.0,) + (0.0,) * 383, "anchor": (0.0, 1.0) + (0.0,) * 382},
        lexical_query="lyra",
    )

    ids = {hit.fact_id for hit in hits}
    assert crossing_fact.id not in ids
    assert active_fact.id in ids
