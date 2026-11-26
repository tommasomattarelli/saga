"""ADR 0022 C1/F1/F2/P1 — hybrid recall wiring and never-fail behaviour."""

import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.ai.context import build_context
from app.ai.embedding_config import legacy_space
from app.ai.prompts.dm import DMPromptContext, DMPromptState, RecalledFact
from app.ai.recalled_memories import _canonical_refs, _fact_ages, recall_facts
from app.memory.context_snapshot import TurnContextSnapshot
from app.memory.document_contracts import (
    CanonicalReference,
    FactEntity,
    FactImportance,
    FactMetadata,
)
from app.memory.recall import PreparedRecallQuery, RecallSnapshot
from app.memory.recall_config import RecallConfig
from app.memory.semantic import HybridHit
from app.models.quest import QuestRecord, QuestRegistry


def _prepared(campaign_id: uuid.UUID, index_id: uuid.UUID) -> PreparedRecallQuery:
    return PreparedRecallQuery(
        uuid.uuid4(),
        campaign_id,
        index_id,
        legacy_space(),
        2,
        {"action": (1.0, 0.0), "anchor": (0.0, 1.0)},
    )


def _snapshot(head_turn_id: uuid.UUID | None = None) -> TurnContextSnapshot:
    campaign_id = uuid.uuid4()
    index_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    return TurnContextSnapshot(
        campaign_id=campaign_id,
        head_turn_id=head_turn_id or turn_id,
        context_epoch=0,
        scene=DMPromptState(
            world_state={"npcs": {"npc-lyra": {"name": "Lyra"}}},
            character_data={},
            world_baseline={},
            quests=QuestRegistry(
                active=[QuestRecord(id="find_lyra", name="Find Lyra", description="Locate Lyra.")]
            ),
        ),
        prompt=DMPromptContext(),
        difficulty="medium",
        history=(),
        policy=None,
        global_checkpoint_id=None,
        intermediate_batch_ids=(),
        recall_snapshot=RecallSnapshot(
            uuid.uuid4(), campaign_id, index_id, 2, legacy_space(), ("Lyra",)
        ),
        ancestry_turn_ids=(turn_id,),
        raw_turn_ids=(turn_id,),
    )


def _hit() -> HybridHit:
    metadata = FactMetadata(
        entities=(
            FactEntity(
                name="Lyra",
                type="npc",
                role="witness",
                canonical_ref=CanonicalReference(type="npc", id="npc-lyra"),
            ),
        ),
        attribution=(0,),
        temporal_references=(),
        importance=FactImportance(level="critical", reason="an explicit promise"),
    )
    return HybridHit(
        fact_id=uuid.uuid4(),
        content="Lyra promised the old map.",
        category="commitment",
        assertion_type="intention",
        fact_metadata=metadata,
        score=0.5,
    )


@pytest.fixture
def env(mocker):
    config = RecallConfig()
    mocker.patch("app.ai.recalled_memories.get_recall_config", return_value=config)
    lexical = mocker.patch(
        "app.ai.recalled_memories.build_lexical_query", return_value="lyra:* | map"
    )
    search = mocker.patch("app.ai.recalled_memories.search_hybrid_facts", return_value=[])
    ages = mocker.patch("app.ai.recalled_memories._fact_ages", return_value={})
    rank = mocker.patch(
        "app.ai.recalled_memories.rank_hits", side_effect=lambda hits, **kwargs: list(hits)
    )
    logger = mocker.patch("app.ai.recalled_memories.logger")
    return SimpleNamespace(
        config=config, lexical=lexical, search=search, ages=ages, rank=rank, logger=logger
    )


@pytest.mark.asyncio
async def test_hybrid_pipeline_maps_hits_to_typed_facts(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)
    hit = _hit()
    env.search.return_value = [hit]
    env.ages.return_value = {hit.fact_id: 7}

    facts = await recall_facts(snapshot, "find the old map", mocker.Mock(), prepared)

    assert facts == (
        RecalledFact(
            content="Lyra promised the old map.",
            category="commitment",
            age_turns=7,
            speaker="Lyra",
            importance="critical",
            assertion_type="intention",
        ),
    )
    call = env.search.call_args.kwargs
    assert call["campaign_id"] == snapshot.campaign_id
    assert call["index_id"] == prepared.index_id
    assert call["dimension"] == prepared.dimension
    assert call["vectors"] == prepared.vectors
    assert call["lexical_query"] == "lyra:* | map"
    assert call["ancestry_turn_ids"] == snapshot.ancestry_turn_ids
    assert call["pool"] == env.config.candidate_pool
    assert call["rrf_k"] == env.config.rrf_k
    assert (call["use_action"], call["use_anchor"], call["use_lexical"]) == (True, True, True)
    rank_call = env.rank.call_args.kwargs
    assert rank_call["canonical_refs"] == frozenset({("npc", "npc-lyra"), ("quest", "find_lyra")})
    assert rank_call["ages"] == {hit.fact_id: 7}
    assert env.logger.info.call_args.kwargs["outcome"] == "ok"


@pytest.mark.asyncio
async def test_lexical_only_when_embedding_unavailable(env, mocker):
    snapshot = _snapshot()

    await recall_facts(snapshot, "find the map", mocker.Mock(), None)

    call = env.search.call_args.kwargs
    assert (call["use_action"], call["use_anchor"], call["use_lexical"]) == (False, False, True)
    assert call["vectors"] == {}
    assert call["index_id"] == snapshot.recall_snapshot.index_id
    assert "lexical" in env.logger.info.call_args.kwargs["branches"]


@pytest.mark.asyncio
async def test_lexical_only_without_recall_snapshot_still_searches(env, mocker):
    snapshot = replace(_snapshot(), recall_snapshot=None)

    await recall_facts(snapshot, "find the map", mocker.Mock(), None)

    call = env.search.call_args.kwargs
    assert call["index_id"] is None
    assert call["dimension"] is None
    assert (call["use_action"], call["use_anchor"], call["use_lexical"]) == (False, False, True)
    assert env.logger.info.call_args.kwargs["outcome"] == "no_results"


@pytest.mark.asyncio
async def test_dense_only_when_lexical_query_is_empty(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)
    env.lexical.return_value = ""

    await recall_facts(snapshot, "wait", mocker.Mock(), prepared)

    call = env.search.call_args.kwargs
    assert (call["use_action"], call["use_anchor"], call["use_lexical"]) == (True, True, False)
    assert "lexical" not in env.logger.info.call_args.kwargs["branches"]


@pytest.mark.asyncio
async def test_no_results_and_branch_failure_are_logged_distinctly(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)

    await recall_facts(snapshot, "wait", mocker.Mock(), prepared)
    assert env.logger.info.call_args.kwargs["outcome"] == "no_results"
    assert env.logger.info.call_args.kwargs["candidates"] == 0
    assert env.logger.info.call_args.kwargs["injected"] == 0
    assert "latency_ms" in env.logger.info.call_args.kwargs
    env.logger.error.assert_not_called()

    env.search.side_effect = RuntimeError("db down")
    facts = await recall_facts(snapshot, "wait", mocker.Mock(), prepared)
    assert facts == ()
    assert env.logger.error.call_args.kwargs["outcome"] == "branch_failure"
    assert "hybrid_search" in env.logger.error.call_args.kwargs["failures"]
    assert env.logger.error.call_args.kwargs["injected"] == 0


@pytest.mark.asyncio
async def test_lexical_branch_failure_keeps_dense_results(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)
    env.lexical.side_effect = RuntimeError("fts down")
    hit = _hit()
    env.search.return_value = [hit]

    facts = await recall_facts(snapshot, "find the map", mocker.Mock(), prepared)

    assert len(facts) == 1
    assert env.search.call_args.kwargs["use_lexical"] is False
    assert "lexical_query" in env.logger.error.call_args.kwargs["failures"]


@pytest.mark.asyncio
async def test_age_lookup_failure_does_not_fail_recall(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)
    env.search.return_value = [_hit()]
    env.ages.side_effect = RuntimeError("turns unavailable")

    facts = await recall_facts(snapshot, "act", mocker.Mock(), prepared)

    assert len(facts) == 1
    assert facts[0].age_turns == 0
    assert "age_lookup" in env.logger.error.call_args.kwargs["failures"]


@pytest.mark.asyncio
async def test_recall_failure_never_breaks_build_context(env, mocker):
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)
    env.search.side_effect = RuntimeError("db down")

    context = await build_context(snapshot, "act", mocker.Mock(), prepared)

    assert context.prompt_context.recalled_memories == ()
    assert context.messages[-1] == {"role": "user", "content": "act"}


@pytest.mark.asyncio
async def test_disabled_recall_skips_retrieval(env, mocker):
    mocker.patch(
        "app.ai.recalled_memories.get_recall_config", return_value=RecallConfig(enabled=False)
    )
    snapshot = _snapshot()
    prepared = _prepared(snapshot.campaign_id, snapshot.recall_snapshot.index_id)

    assert await recall_facts(snapshot, "act", mocker.Mock(), prepared) == ()
    env.search.assert_not_called()
    env.logger.info.assert_not_called()
    env.logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_unexpected_config_failure_returns_empty_facts(env, mocker):
    mocker.patch(
        "app.ai.recalled_memories.get_recall_config", side_effect=RuntimeError("bad config")
    )
    snapshot = _snapshot()

    assert await recall_facts(snapshot, "act", mocker.Mock(), None) == ()
    assert env.logger.error.call_args.kwargs["outcome"] == "branch_failure"
    assert "unexpected" in env.logger.error.call_args.kwargs["failures"]


@pytest.mark.asyncio
async def test_fact_ages_subtract_source_depth_from_head_depth(mocker):
    snapshot = _snapshot(head_turn_id=uuid.uuid4())
    fact_id, unjoined_id = uuid.uuid4(), uuid.uuid4()
    db = mocker.Mock()
    db.scalar = mocker.AsyncMock(return_value=10)
    result = mocker.Mock()
    result.all.return_value = [(fact_id, 3)]
    db.execute = mocker.AsyncMock(return_value=result)

    assert await _fact_ages(db, snapshot, [fact_id, unjoined_id]) == {fact_id: 7}
    db.execute.assert_awaited_once()


def test_canonical_refs_come_from_world_state_npcs_and_all_quest_statuses():
    snapshot = _snapshot()
    quests = snapshot.scene.quests
    quests.completed.append(QuestRecord(id="old_deed", name="Old Deed"))

    assert _canonical_refs(snapshot.scene) == frozenset(
        {("npc", "npc-lyra"), ("quest", "find_lyra"), ("quest", "old_deed")}
    )
