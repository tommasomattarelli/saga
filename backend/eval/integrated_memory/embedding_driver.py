from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app import dependencies
from app.ai.router import get_user_embedding
from app.memory import embedding_batch as batch
from app.memory import embedding_queue, embedding_worker
from app.models.memory_fact import MemoryFactSource
from app.models.source_embedding import SourceEmbedding
from eval.integrated_memory.evidence_io import append_json
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger
from eval.integrated_memory.plan import IntegratedPlan, resolve_effective_embedding
from eval.integrated_memory.provider_guard import guard_embedding_attempts
from eval.support.digest import digest


async def drain_embeddings(
    plan: IntegratedPlan, ledger: IntegratedLedger, campaign_id: UUID, directory: Path
) -> None:
    cfg = embedding_queue.get_rebuild_config()
    if plan.embedding_request_cap is None:
        raise ValueError("embedding request cap is required")
    async with dependencies.async_session() as db:
        claim = await batch.claim_work(db, campaign_id, cfg)
        await db.commit()
    for _ in range(plan.embedding_request_cap + 2):
        ledger.ensure_healthy()
        if claim is None:
            return
        if claim.kind == "cutover":
            async with dependencies.async_session() as db:
                published = await embedding_worker.cutover(db, claim, cfg)
                await db.commit()
            if not published:
                raise ValueError("embedding index did not complete; review the persisted queue")
            return
        space = batch.manifest_space(claim)
        if space != plan.embedding_space:
            raise ValueError("embedding index space differs from the frozen manifest")
        async with dependencies.async_session() as db:
            turn_ids = tuple(
                await db.scalars(
                    select(MemoryFactSource.turn_id)
                    .join(
                        SourceEmbedding, SourceEmbedding.memory_fact_id == MemoryFactSource.fact_id
                    )
                    .where(SourceEmbedding.id.in_(claim.row_ids))
                    .distinct()
                    .order_by(MemoryFactSource.turn_id)
                )
            )
        scope = AttemptScope(
            run_id=plan.run_id,
            campaign_id=campaign_id,
            source_turn_ids=turn_ids,
            source_embedding_ids=tuple(claim.row_ids),
            index_id=claim.index_id,
            input_hash=digest(
                {"rows": [str(row) for row in claim.row_ids], "hashes": claim.hashes}
            ),
            role="embedding",
            provider=space.provider,
            model=space.model,
        )
        await embedding_worker._pace(cfg.rebuild_min_interval_seconds)
        try:
            resolved = resolve_effective_embedding(
                plan, await get_user_embedding(claim.owner_id, space=space)
            )
            append_json(
                directory / "embedding-inputs.jsonl",
                {
                    "scope": scope.model_dump(mode="json"),
                    "space": asdict(space),
                    "texts": claim.texts,
                },
            )
            with (
                ledger.scope(scope),
                guard_embedding_attempts(
                    ledger,
                    model=space.model,
                    provider=space.provider,
                    texts=claim.texts,
                    policy=plan.embedding_policy,
                ),
            ):
                result = await embedding_queue.embed_texts_via_provider(claim.texts, resolved)
        except BaseException:
            await batch.mark_failed(claim, "Integrated evaluation stopped; review evidence.", cfg)
            raise
        async with dependencies.async_session() as db:
            saved = await batch.save_vectors(db, claim, result, cfg)
            await db.commit()
        if not saved:
            raise ValueError("embedding vectors were not published; review the persisted queue")
        ledger.ensure_healthy()
        async with dependencies.async_session() as db:
            claim = await batch.next_batch(db, claim, cfg)
            await db.commit()
    raise ValueError("embedding queue exceeded the planned fact-content bound")
