from __future__ import annotations

import time
from collections.abc import Sequence
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.dm import DMPromptState, RecalledFact
from app.memory.context_snapshot import TurnContextSnapshot
from app.memory.query_construction import build_gazetteer, build_lexical_query
from app.memory.ranking import rank_hits
from app.memory.recall import PreparedRecallQuery
from app.memory.recall_config import get_recall_config
from app.memory.semantic import HybridHit, search_hybrid_facts
from app.models.memory_batch import MemoryBatchTurn
from app.models.memory_fact import MemoryFactSource
from app.models.quest import QuestStatus
from app.models.turn import Turn

logger = structlog.get_logger()


def _canonical_refs(scene: DMPromptState) -> frozenset[tuple[str, str]]:
    refs = {("npc", str(npc_id)) for npc_id in scene.world_state.get("npcs", {})}
    for status in QuestStatus:
        refs.update(("quest", quest.id) for quest in getattr(scene.quests, status.value))
    return frozenset(refs)


def _speaker(hit: HybridHit) -> str | None:
    metadata = hit.fact_metadata
    if metadata is None or not metadata.attribution:
        return None
    index = metadata.attribution[0]
    return metadata.entities[index].name if index < len(metadata.entities) else None


async def _fact_ages(
    db: AsyncSession, snapshot: TurnContextSnapshot, fact_ids: Sequence[UUID]
) -> dict[UUID, int]:
    if not fact_ids or snapshot.head_turn_id is None:
        return {}
    head_depth = await db.scalar(
        select(Turn.history_depth).where(Turn.id == snapshot.head_turn_id)
    )
    if head_depth is None:
        return {}
    rows = (
        await db.execute(
            select(MemoryFactSource.fact_id, func.max(Turn.history_depth))
            .join(
                MemoryBatchTurn,
                (MemoryBatchTurn.batch_id == MemoryFactSource.batch_id)
                & (MemoryBatchTurn.turn_id == MemoryFactSource.turn_id)
                & (MemoryBatchTurn.campaign_id == MemoryFactSource.campaign_id),
            )
            .join(Turn, Turn.id == MemoryBatchTurn.turn_id)
            .where(
                MemoryFactSource.fact_id.in_(fact_ids),
                MemoryFactSource.campaign_id == snapshot.campaign_id,
                Turn.id.in_(snapshot.ancestry_turn_ids),
                Turn.history_depth.is_not(None),
            )
            .group_by(MemoryFactSource.fact_id)
        )
    ).all()
    return {
        fact_id: head_depth - depth
        for fact_id, depth in rows
        if depth is not None and head_depth >= depth
    }


async def recall_facts(
    snapshot: TurnContextSnapshot,
    player_action: str,
    db: AsyncSession,
    query_embedding: PreparedRecallQuery | None,
) -> tuple[RecalledFact, ...]:
    started = time.perf_counter()
    branches: list[str] = []
    unavailable: list[str] = []
    failures: list[str] = []
    error: str | None = None
    hits: list[HybridHit] = []
    facts: tuple[RecalledFact, ...] = ()

    try:
        config = get_recall_config()
        if not config.enabled:
            return ()

        recall_snapshot = snapshot.recall_snapshot
        index_id = (
            query_embedding.index_id
            if query_embedding is not None
            else (recall_snapshot.index_id if recall_snapshot else None)
        )
        dimension = (
            query_embedding.dimension
            if query_embedding is not None
            else (recall_snapshot.dimension if recall_snapshot else None)
        )

        use_dense = query_embedding is not None
        if use_dense:
            branches.extend(("action", "anchor"))
        else:
            unavailable.append("dense")

        matching_names = build_gazetteer(
            snapshot.scene.world_state,
            snapshot.scene.world_baseline,
            recall_snapshot.known_names if recall_snapshot else (),
        )
        lexical_query = ""
        try:
            lexical_query = await build_lexical_query(db, player_action, matching_names)
        except Exception:
            failures.append("lexical_query")
        if lexical_query:
            branches.append("lexical")
        else:
            unavailable.append("lexical")

        if branches:
            try:
                hits = await search_hybrid_facts(
                    db,
                    campaign_id=snapshot.campaign_id,
                    index_id=index_id,
                    dimension=dimension,
                    vectors=query_embedding.vectors if query_embedding is not None else {},
                    lexical_query=lexical_query,
                    ancestry_turn_ids=snapshot.ancestry_turn_ids,
                    pool=config.candidate_pool,
                    rrf_k=config.rrf_k,
                    use_action=use_dense,
                    use_anchor=use_dense,
                    use_lexical=bool(lexical_query),
                )
            except Exception as exc:
                failures.append("hybrid_search")
                error = str(exc)[:200]
        else:
            unavailable.append("search")

        ages: dict[UUID, int] = {}
        if hits:
            try:
                ages = await _fact_ages(db, snapshot, [hit.fact_id for hit in hits])
            except Exception:
                failures.append("age_lookup")

        try:
            ranked = rank_hits(
                hits,
                config=config,
                gazetteer=matching_names,
                canonical_refs=_canonical_refs(snapshot.scene),
                ages=ages,
            )
        except Exception:
            failures.append("ranking")
            ranked = []

        facts = tuple(
            RecalledFact(
                content=hit.content,
                category=hit.category or "information",
                age_turns=ages.get(hit.fact_id, 0),
                speaker=_speaker(hit),
                importance=(
                    hit.fact_metadata.importance.level if hit.fact_metadata else "ordinary"
                ),
                assertion_type=hit.assertion_type or "statement",
            )
            for hit in ranked
            if hit.content.strip()
        )
    except Exception as exc:
        failures.append("unexpected")
        error = str(exc)[:200]

    outcome = "ok"
    if failures or not branches:
        outcome = "branch_failure"
    elif not facts:
        outcome = "no_results"

    log = logger.error if outcome == "branch_failure" else logger.info
    log(
        "recall_lookup",
        campaign_id=str(snapshot.campaign_id),
        outcome=outcome,
        branches=tuple(branches),
        unavailable=tuple(unavailable),
        failures=tuple(failures),
        error=error,
        candidates=len(hits),
        injected=len(facts),
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return facts
