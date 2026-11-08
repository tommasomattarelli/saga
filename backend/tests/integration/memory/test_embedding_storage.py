"""ADR 0018 point 5 — real-PostgreSQL invariants of the versioned embedding storage."""

import hashlib
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.dependencies import async_session, engine
from app.models.campaign import Campaign, Difficulty
from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import (
    EmbeddingSourceType,
    EmbeddingWorkState,
    SourceEmbedding,
)
from app.models.turn import Turn
from app.models.user import User

_PIPELINE = "embed-v1"


def _index(campaign_id: uuid.UUID, **overrides: Any) -> EmbeddingIndex:
    defaults: dict[str, Any] = {
        "provider": "openrouter",
        "model": "test-model",
        "pipeline_version": _PIPELINE,
        "dimension": 1536,
        "is_active": False,
        "rebuild_state": EmbeddingRebuildState.QUEUED,
    }
    defaults.update(overrides)
    return EmbeddingIndex(campaign_id=campaign_id, **defaults)


def _source(index_id: uuid.UUID, campaign_id: uuid.UUID, **overrides: Any) -> SourceEmbedding:
    defaults: dict[str, Any] = {"text_hash": "a" * 64, "work_state": EmbeddingWorkState.PENDING}
    defaults.update(overrides)
    return SourceEmbedding(index_id=index_id, campaign_id=campaign_id, **defaults)


async def _extra_campaign() -> Campaign:
    async with async_session() as db:
        user = User(
            username=f"other_{uuid.uuid4().hex[:10]}",
            email=f"other_{uuid.uuid4().hex[:10]}@example.com",
            hashed_password="pw",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        other = Campaign(user_id=user.id, world_slug="w", name="other", difficulty=Difficulty.EASY)
        db.add(other)
        await db.commit()
        return other


@pytest.fixture
async def campaign(db_session) -> Campaign:
    user = User(
        username=f"u_{uuid.uuid4().hex[:10]}",
        email=f"u_{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    c = Campaign(user_id=user.id, world_slug="w", name="c", difficulty=Difficulty.MEDIUM)
    db_session.add(c)
    await db_session.commit()
    return c


@pytest.fixture
async def seeded_sources(campaign: Campaign, db_session) -> tuple[Turn, MemoryFact]:
    turn = Turn(
        campaign_id=campaign.id,
        turn_number=1,
        player_action="strike",
        narration="The goblin flees.",
        model_used="test-model",
        summary="The player struck and the goblin fled.",
    )
    fact = MemoryFact(
        campaign_id=campaign.id,
        turn_number=1,
        entity_name="Goblin",
        entity_type="npc",
        content="The goblin fled.",
    )
    db_session.add_all([turn, fact])
    await db_session.commit()
    return turn, fact


@pytest.fixture
async def indexed_pair(campaign: Campaign, seeded_sources: tuple[Turn, MemoryFact], db_session):
    turn, fact = seeded_sources
    idx = _index(
        campaign.id, dimension=384, is_active=True, rebuild_state=EmbeddingRebuildState.COMPLETED
    )
    db_session.add(idx)
    await db_session.commit()
    return idx, turn, fact


async def _expect_integrity_error(sql: str, params: dict[str, Any]) -> None:
    async with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(text(sql), params)


# --- index invariants -------------------------------------------------------


async def test_one_active_index_per_campaign(campaign: Campaign, db_session) -> None:
    db_session.add(
        _index(campaign.id, is_active=True, rebuild_state=EmbeddingRebuildState.COMPLETED)
    )
    await db_session.commit()
    await _expect_integrity_error(
        "INSERT INTO embedding_indexes (id, campaign_id, provider, model, pipeline_version,"
        " dimension, is_active, rebuild_state)"
        " VALUES (gen_random_uuid(), :cid, 'openrouter', 'other', 'embed-v1', 1536, true, 'completed')",
        {"cid": campaign.id},
    )


async def test_source_and_queue_rollback_together(campaign: Campaign, db_session) -> None:
    from app.memory.embedding_queue import enqueue_source_embedding

    index = _index(campaign.id, is_active=True, rebuild_state=EmbeddingRebuildState.COMPLETED)
    db_session.add(index)
    await db_session.commit()
    index_id = index.id
    turn = Turn(
        campaign_id=campaign.id,
        turn_number=77,
        player_action="test",
        narration="test",
        model_used="test-model",
        summary="rollback summary",
    )
    db_session.add(turn)
    await db_session.flush()
    await enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.TURN,
        source_id=turn.id,
        source_text=turn.summary,
    )
    await db_session.rollback()

    assert await db_session.scalar(select(Turn).where(Turn.turn_number == 77)) is None
    assert (
        await db_session.scalar(
            select(SourceEmbedding).where(SourceEmbedding.index_id == index_id)
        )
        is None
    )


@pytest.mark.parametrize(
    ("old_dimension", "new_dimension", "legacy"), [(3, 3, False), (384, 1536, True)]
)
async def test_recall_stays_on_snapshotted_index_with_vectors_after_cutover(
    campaign: Campaign,
    db_session,
    assert_no_db_held,
    old_dimension: int,
    new_dimension: int,
    legacy: bool,
) -> None:
    from app.ai.embedding_config import EmbeddingBatch
    from app.memory.recall import embed_recall_query, snapshot_recall_query
    from app.memory.semantic import search_similar_facts
    from app.models.embedding_index import text_hash

    old_index = _index(
        campaign.id,
        provider="openai" if legacy else "openrouter",
        model="text-embedding-3-small" if legacy else "test-model",
        pipeline_version="embed-v1-legacy" if legacy else "embed-v1",
        dimension=old_dimension,
        endpoint_identity="https://api.openai.com/v1"
        if legacy
        else "https://openrouter.ai/api/v1",
        is_active=True,
        rebuild_state=EmbeddingRebuildState.COMPLETED,
    )
    fact = MemoryFact(
        campaign_id=campaign.id,
        turn_number=1,
        entity_name="Rook",
        entity_type="npc",
        content="Rook guards the northern gate.",
    )
    db_session.add_all([old_index, fact])
    await db_session.flush()
    db_session.add(
        _source(
            old_index.id,
            campaign.id,
            source_type=EmbeddingSourceType.MEMORY_FACT,
            memory_fact_id=fact.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.1] * old_dimension,
        )
    )
    await db_session.commit()
    old_index_id = old_index.id
    snapshot = await snapshot_recall_query(db_session, campaign.id)
    assert snapshot is not None
    await db_session.close()

    async def swap_active_and_embed(space, query, *, user_id):
        assert_no_db_held()
        assert space.requested_dimensions == (384 if legacy else None)
        target_id = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE embedding_indexes SET is_active = false WHERE campaign_id = :cid"),
                {"cid": campaign.id},
            )
            await conn.execute(
                text(
                    "INSERT INTO embedding_indexes (id, campaign_id, provider, model, endpoint_identity,"
                    " pipeline_version, dimension, is_active, rebuild_state) VALUES (:id, :cid,"
                    " 'openrouter', 'different-model', 'https://openrouter.ai/api/v1',"
                    " 'embed-v1', :dimension, true, 'completed')"
                ),
                {"id": target_id, "cid": campaign.id, "dimension": new_dimension},
            )
            await conn.execute(
                text(
                    "INSERT INTO source_embeddings (id, index_id, campaign_id, source_type,"
                    " memory_fact_id, text_hash, embedding, work_state) VALUES (gen_random_uuid(),"
                    " :index_id, :cid, 'memory_fact', :fact_id, :text_hash, CAST(:vector AS vector),"
                    " 'embedded')"
                ),
                {
                    "index_id": target_id,
                    "cid": campaign.id,
                    "fact_id": fact.id,
                    "text_hash": text_hash(fact.content),
                    "vector": str([0.2] * new_dimension),
                },
            )
        return EmbeddingBatch(space, old_dimension, (tuple([0.1] * old_dimension),))

    with patch("app.memory.recall.embed_query_for_index", new=swap_active_and_embed):
        prepared = await embed_recall_query(snapshot, "who guards the gate?")
    assert prepared is not None
    assert prepared.index_id == old_index_id
    assert prepared.dimension == old_dimension
    async with async_session() as db:
        facts = await search_similar_facts(campaign.id, "ignored", db, query_embedding=prepared)
    assert [item.id for item in facts] == [fact.id]

    async def failed_query(space, query, *, user_id):
        assert_no_db_held()
        raise RuntimeError("provider unavailable")

    with patch("app.memory.recall.embed_query_for_index", new=failed_query):
        assert await embed_recall_query(snapshot, "who guards the gate?") is None


@pytest.mark.parametrize("scenario", ["empty", "unknown_dimension", "pending_fact", "turn_only"])
async def test_recall_skips_provider_for_indexes_without_recallable_facts(
    campaign: Campaign, db_session, scenario: str
) -> None:
    from unittest.mock import AsyncMock, patch

    from app.memory.recall import snapshot_recall_query

    index = _index(
        campaign.id,
        dimension=None if scenario == "unknown_dimension" else 384,
        endpoint_identity="https://api.openai.com/v1",
        is_active=True,
        rebuild_state=EmbeddingRebuildState.COMPLETED,
    )
    db_session.add(index)
    if scenario in {"pending_fact", "turn_only"}:
        turn = Turn(
            campaign_id=campaign.id,
            turn_number=1,
            player_action="look",
            narration="A guard stands watch.",
            model_used="test",
            summary="A guard watches the gate.",
        )
        fact = MemoryFact(
            campaign_id=campaign.id,
            turn_number=1,
            entity_name="Guard",
            entity_type="npc",
            content="A guard watches the gate.",
        )
        db_session.add_all([turn, fact])
        await db_session.flush()
        if scenario == "turn_only":
            db_session.add(
                _source(
                    index.id,
                    campaign.id,
                    source_type=EmbeddingSourceType.TURN,
                    turn_id=turn.id,
                    work_state=EmbeddingWorkState.EMBEDDED,
                    embedding=[0.1] * 384,
                )
            )
        else:
            db_session.add(
                _source(
                    index.id,
                    campaign.id,
                    source_type=EmbeddingSourceType.MEMORY_FACT,
                    memory_fact_id=fact.id,
                    work_state=EmbeddingWorkState.PENDING,
                )
            )
    await db_session.commit()

    provider = AsyncMock()
    with patch("app.memory.recall.embed_query_for_index", new=provider):
        snapshot = await snapshot_recall_query(db_session, campaign.id)
    assert snapshot is None
    provider.assert_not_called()


async def test_recall_rejects_query_prepared_for_another_campaign(
    campaign: Campaign, db_session
) -> None:
    from app.ai.embedding_config import legacy_space
    from app.memory.recall import PreparedRecallQuery
    from app.memory.semantic import search_similar_facts

    other = await _extra_campaign()
    prepared = PreparedRecallQuery(
        campaign.user_id,
        campaign.id,
        uuid.uuid4(),
        legacy_space(),
        384,
        (0.1,) * 384,
    )
    assert (
        await search_similar_facts(other.id, "query", db_session, query_embedding=prepared) == []
    )


async def test_active_requires_completed_state(campaign: Campaign, db_session) -> None:
    db_session.add(
        _index(campaign.id, is_active=True, rebuild_state=EmbeddingRebuildState.RUNNING)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_cutover_keeps_one_active_in_a_single_statement(
    campaign: Campaign, db_session
) -> None:
    """A partial unique index is not deferrable, so closing the old active index
    and activating the target must be one statement; two statements would expose
    two active rows mid-transaction."""
    old = _index(campaign.id, is_active=True, rebuild_state=EmbeddingRebuildState.COMPLETED)
    new = _index(
        campaign.id, model="new", is_active=False, rebuild_state=EmbeddingRebuildState.RUNNING
    )
    db_session.add_all([old, new])
    await db_session.commit()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE embedding_indexes SET is_active = (id = :new),"
                " rebuild_state = CASE WHEN id = :new THEN 'completed' ELSE rebuild_state END"
                " WHERE id IN (:new, :old)"
            ),
            {"new": new.id, "old": old.id},
        )
        active = (
            (await conn.execute(text("SELECT id FROM embedding_indexes WHERE is_active")))
            .scalars()
            .all()
        )
        assert active == [new.id]


async def test_one_open_rebuild_per_campaign(campaign: Campaign, db_session) -> None:
    db_session.add(_index(campaign.id, rebuild_state=EmbeddingRebuildState.QUEUED))
    await db_session.commit()
    await _expect_integrity_error(
        "INSERT INTO embedding_indexes (id, campaign_id, provider, model, pipeline_version,"
        " dimension, is_active, rebuild_state)"
        " VALUES (gen_random_uuid(), :cid, 'openrouter', 'other', 'embed-v1', 1536, false, 'running')",
        {"cid": campaign.id},
    )


async def test_states_are_stored_as_values(campaign: Campaign, db_session) -> None:
    db_session.add(_index(campaign.id))
    await db_session.commit()
    row = (
        await db_session.execute(text("SELECT rebuild_state FROM embedding_indexes"))
    ).fetchone()
    assert row == ("queued",)


async def test_terminal_states_do_not_block_a_new_rebuild(campaign: Campaign, db_session) -> None:
    for state in (
        EmbeddingRebuildState.COMPLETED,
        EmbeddingRebuildState.FAILED,
        EmbeddingRebuildState.CANCELLED,
    ):
        db_session.add(_index(campaign.id, rebuild_state=state))
        await db_session.commit()
    db_session.add(_index(campaign.id, rebuild_state=EmbeddingRebuildState.QUEUED, model="new"))
    await db_session.commit()
    count = (await db_session.execute(text("SELECT count(*) FROM embedding_indexes"))).scalar()
    assert count == 4


async def test_dimension_must_be_positive(campaign: Campaign, db_session) -> None:
    db_session.add(_index(campaign.id, dimension=0))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_dimension_unknown_until_first_observation(campaign: Campaign, db_session) -> None:
    db_session.add(_index(campaign.id, dimension=None))
    await db_session.commit()
    dim = (await db_session.execute(text("SELECT dimension FROM embedding_indexes"))).scalar()
    assert dim is None


async def test_index_claim_fields_default_null(campaign: Campaign, db_session) -> None:
    db_session.add(_index(campaign.id))
    await db_session.commit()
    row = (
        await db_session.execute(text("SELECT claim_token, claimed_at FROM embedding_indexes"))
    ).fetchone()
    assert row == (None, None)


# --- source invariants ------------------------------------------------------


async def test_exactly_one_reference_per_source(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, fact = indexed_pair
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            memory_fact_id=fact.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_source_requires_one_reference(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    db_session.add(_source(idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_source_kind_must_match_reference(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, _, fact = indexed_pair
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            memory_fact_id=fact.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_source_campaign_must_match_index_campaign(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    other = await _extra_campaign()
    db_session.add(
        _source(idx.id, other.id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_turn_must_belong_to_the_source_campaign(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    other = await _extra_campaign()
    fact = MemoryFact(
        campaign_id=other.id, turn_number=1, entity_name="e", entity_type="npc", content="c"
    )
    db_session.add(fact)
    await db_session.commit()
    db_session.add(
        _source(idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id)
    )
    await db_session.commit()
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.MEMORY_FACT,
            memory_fact_id=fact.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_per_version_source_uniqueness(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, fact = indexed_pair
    db_session.add_all(
        [
            _source(
                idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id
            ),
            _source(
                idx.id,
                idx.campaign_id,
                source_type=EmbeddingSourceType.MEMORY_FACT,
                memory_fact_id=fact.id,
            ),
        ]
    )
    await db_session.commit()
    await _expect_integrity_error(
        "INSERT INTO source_embeddings (id, index_id, campaign_id, source_type, turn_id,"
        " memory_fact_id, text_hash)"
        " VALUES (gen_random_uuid(), :ii, :cid, 'turn', :tid, NULL, 'h')",
        {"ii": idx.id, "cid": idx.campaign_id, "tid": turn.id},
    )
    await _expect_integrity_error(
        "INSERT INTO source_embeddings (id, index_id, campaign_id, source_type, turn_id,"
        " memory_fact_id, text_hash)"
        " VALUES (gen_random_uuid(), :ii, :cid, 'memory_fact', NULL, :fid, 'h')",
        {"ii": idx.id, "cid": idx.campaign_id, "fid": fact.id},
    )


async def test_same_source_can_exist_across_versions(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    other_idx = _index(idx.campaign_id, model="other", rebuild_state=EmbeddingRebuildState.FAILED)
    db_session.add(other_idx)
    await db_session.commit()
    db_session.add(
        _source(idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id)
    )
    db_session.add(
        _source(
            other_idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id
        )
    )
    await db_session.commit()
    count = (await db_session.execute(text("SELECT count(*) FROM source_embeddings"))).scalar()
    assert count == 2


async def test_embedded_requires_a_vector(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=None,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_pending_source_is_the_queue(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    row = _source(idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id)
    db_session.add(row)
    await db_session.commit()
    state = (await db_session.execute(text("SELECT work_state FROM source_embeddings"))).fetchone()
    assert state == ("pending",)


async def test_work_state_stored_as_values(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.1] * 384,
        )
    )
    await db_session.commit()
    row = (await db_session.execute(text("SELECT work_state FROM source_embeddings"))).fetchone()
    assert row == ("embedded",)


async def test_text_hash_is_the_sha256_of_the_embedded_text(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, _ = indexed_pair
    expected = hashlib.sha256(turn.summary.encode()).hexdigest()
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            text_hash=expected,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.5] * 384,
        )
    )
    await db_session.commit()
    refhash = (
        await db_session.execute(
            text("SELECT encode(sha256(convert_to(:txt,'UTF8')),'hex')"), {"txt": turn.summary}
        )
    ).scalar()
    stored_text_hash = (
        await db_session.execute(text("SELECT text_hash FROM source_embeddings"))
    ).fetchone()
    assert stored_text_hash == (expected,)
    assert expected == refhash


async def test_variable_dimensions_coexist_across_versions(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    """384 legacy and native 1536 never share a dimension: each version carries
    its own vectors and the two are tracked separately."""
    idx, turn, fact = indexed_pair
    native_idx = _index(
        idx.campaign_id,
        dimension=1536,
        model="native-1536",
        rebuild_state=EmbeddingRebuildState.FAILED,
    )
    db_session.add(native_idx)
    await db_session.commit()
    db_session.add(
        _source(
            idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.1] * 384,
        )
    )
    db_session.add(
        _source(
            native_idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.2] * 1536,
        )
    )
    db_session.add(
        _source(
            native_idx.id,
            idx.campaign_id,
            source_type=EmbeddingSourceType.MEMORY_FACT,
            memory_fact_id=fact.id,
            work_state=EmbeddingWorkState.EMBEDDED,
            embedding=[0.3] * 1536,
        )
    )
    await db_session.commit()

    legacy_dim = (
        await db_session.execute(
            text("SELECT vector_dims(embedding) FROM source_embeddings WHERE index_id = :i"),
            {"i": idx.id},
        )
    ).scalar()
    native_dims = set(
        (
            await db_session.execute(
                text("SELECT vector_dims(embedding) FROM source_embeddings WHERE index_id = :i"),
                {"i": native_idx.id},
            )
        )
        .scalars()
        .all()
    )
    assert legacy_dim == 384
    assert native_dims == {1536}


# --- deletion ---------------------------------------------------------------


async def test_deleting_index_cascades_sources(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, fact = indexed_pair
    db_session.add_all(
        [
            _source(
                idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id
            ),
            _source(
                idx.id,
                idx.campaign_id,
                source_type=EmbeddingSourceType.MEMORY_FACT,
                memory_fact_id=fact.id,
            ),
        ]
    )
    await db_session.commit()

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM embedding_indexes WHERE id = :i"), {"i": idx.id})
    count = (await db_session.execute(text("SELECT count(*) FROM source_embeddings"))).scalar()
    assert count == 0


async def test_deleting_turn_cascades_its_source(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, fact = indexed_pair
    db_session.add_all(
        [
            _source(
                idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id
            ),
            _source(
                idx.id,
                idx.campaign_id,
                source_type=EmbeddingSourceType.MEMORY_FACT,
                memory_fact_id=fact.id,
            ),
        ]
    )
    await db_session.commit()

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM turns WHERE id = :t"), {"t": turn.id})
    rows = (
        (await db_session.execute(text("SELECT memory_fact_id FROM source_embeddings")))
        .scalars()
        .all()
    )
    assert rows == [fact.id]


async def test_deleting_memory_fact_cascades_its_source(
    indexed_pair: tuple[EmbeddingIndex, Turn, MemoryFact], db_session
) -> None:
    idx, turn, fact = indexed_pair
    db_session.add_all(
        [
            _source(
                idx.id, idx.campaign_id, source_type=EmbeddingSourceType.TURN, turn_id=turn.id
            ),
            _source(
                idx.id,
                idx.campaign_id,
                source_type=EmbeddingSourceType.MEMORY_FACT,
                memory_fact_id=fact.id,
            ),
        ]
    )
    await db_session.commit()

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM memory_facts WHERE id = :f"), {"f": fact.id})
    rows = (
        (await db_session.execute(text("SELECT turn_id FROM source_embeddings"))).scalars().all()
    )
    assert rows == [turn.id]


# --- schema contract -------------------------------------------------------


async def test_required_indexes_and_constraints_exist(db_session) -> None:
    indexes = (
        (
            await db_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
                    " AND indexname IN (:a, :b, :c, :d)"
                ),
                {
                    "a": "uq_embedding_indexes_campaign_active",
                    "b": "uq_embedding_indexes_campaign_open_rebuild",
                    "c": "uq_source_embeddings_index_turn",
                    "d": "uq_source_embeddings_index_memory_fact",
                },
            )
        )
        .scalars()
        .all()
    )
    assert set(indexes) == {
        "uq_embedding_indexes_campaign_active",
        "uq_embedding_indexes_campaign_open_rebuild",
        "uq_source_embeddings_index_turn",
        "uq_source_embeddings_index_memory_fact",
    }
    constraints = (
        (
            await db_session.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname IN"
                    " ('uq_turns_id_campaign', 'uq_memory_facts_id_campaign',"
                    "  'ck_source_embeddings_single_source',"
                    "  'ck_source_embeddings_kind_matches_reference',"
                    "  'ck_source_embeddings_embedded_has_vector',"
                    "  'ck_embedding_indexes_active_completed',"
                    "  'ck_embedding_indexes_dimension_positive')"
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(constraints) == {
        "uq_turns_id_campaign",
        "uq_memory_facts_id_campaign",
        "ck_source_embeddings_single_source",
        "ck_source_embeddings_kind_matches_reference",
        "ck_source_embeddings_embedded_has_vector",
        "ck_embedding_indexes_active_completed",
        "ck_embedding_indexes_dimension_positive",
    }


async def test_legacy_vector_columns_untouched_at_the_prechange_checkpoint() -> None:
    """Checkpoint contract: Turn/MemoryFact keep the 384-dim legacy column until
    the callers are rewired; the new table's vector is dimensionless."""
    assert Turn.__table__.c["embedding"].type.dim == 384
    assert MemoryFact.__table__.c["embedding"].type.dim == 384
    assert SourceEmbedding.__table__.c["embedding"].type.dim is None
