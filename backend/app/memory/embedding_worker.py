"""ADR 0018 B — the embedding worker loop, cutover, pacing and cooperative stop.

One finite loop. Pacing is a single gate across every rebuild request, including
active maintenance, and is applied with no DB session open. A stop observed
between batches releases the lease and leaves the work persisted; a cutover that
finds new sources releases its claim instead of sleeping on the lease.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.memory import embedding_batch as batch
from app.memory import embedding_lifecycle as lifecycle
from app.memory import embedding_queue
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State

if TYPE_CHECKING:
    from app.ai.embedding_config import EmbeddingRebuildConfig
    from app.memory.embedding_batch import Claim

logger = structlog.get_logger()

_monotonic = time.monotonic
_sleep = asyncio.sleep
_last_request_at: float = 0.0

_stop = asyncio.Event()
_wake = asyncio.Event()
_task: asyncio.Task[None] | None = None


async def _pace(min_interval: float) -> None:
    global _last_request_at
    if min_interval > 0:
        wait = _last_request_at + min_interval - _monotonic()
        if wait > 0:
            await _sleep(wait)
    _last_request_at = _monotonic()


async def cutover(db: AsyncSession, claim: Claim, cfg: EmbeddingRebuildConfig) -> bool:
    await lifecycle.lock_campaign(db, claim.campaign_id)
    index = await batch.load_lease(db, claim, cfg, lock=True)
    if index is None or index.rebuild_state is not State.RUNNING:
        return False
    await embedding_queue.reconcile_index_sources(db, index)
    unfinished = await db.execute(
        text(
            "SELECT count(*) FROM source_embeddings"
            " WHERE index_id = :iid AND work_state <> 'embedded'"
        ),
        {"iid": index.id},
    )
    if (unfinished.scalar() or 0) > 0:
        index.claim_token = None
        index.claimed_at = None
        return False
    await db.execute(
        update(EmbeddingIndex)
        .where(
            EmbeddingIndex.campaign_id == claim.campaign_id,
            EmbeddingIndex.is_active.is_(True),
            EmbeddingIndex.id != index.id,
        )
        .values(is_active=False)
    )
    await db.flush()
    await db.execute(
        update(EmbeddingIndex)
        .where(EmbeddingIndex.id == index.id)
        .values(
            is_active=True,
            rebuild_state=State.COMPLETED,
            claim_token=None,
            claimed_at=None,
            last_error=None,
        )
    )
    await lifecycle.cleanup_superseded_indexes(db, claim.campaign_id, index.id)
    return True


async def process_campaign_once(campaign_id: uuid.UUID) -> bool:
    """Claim one campaign and drive it to a cutover, a failure, or a stop."""
    cfg = embedding_queue.get_rebuild_config()
    async with dependencies.async_session() as db:
        claim = await batch.claim_work(db, campaign_id, cfg)
        await db.commit()
    if claim is None:
        return False
    while True:
        if _stop.is_set():
            await batch.release_claim(claim, cfg)
            return False
        if claim.kind == "cutover":
            async with dependencies.async_session() as db:
                acted = await cutover(db, claim, cfg)
                await db.commit()
            return acted
        await _pace(cfg.rebuild_min_interval_seconds)
        try:
            resolved = await embedding_queue.resolve_embedding(
                claim.owner_id, space=batch.manifest_space(claim)
            )
            result = await embedding_queue.embed_texts_via_provider(claim.texts, resolved)
        except Exception as exc:
            logger.warning("embedding_batch_failed", index_id=str(claim.index_id))
            await batch.mark_failed(claim, lifecycle.short_reason(exc), cfg)
            return False
        async with dependencies.async_session() as db:
            saved = await batch.save_vectors(db, claim, result, cfg)
            await db.commit()
        if not saved:
            return False
        if _stop.is_set():
            await batch.release_claim(claim, cfg)
            return False
        async with dependencies.async_session() as db:
            following = await batch.next_batch(db, claim, cfg)
            await db.commit()
        if following is None:
            return True
        claim = following


async def scan_once() -> int:
    async with dependencies.async_session() as db:
        rows = await db.execute(
            text(
                "SELECT ei.campaign_id,"
                "       min(CASE WHEN ei.rebuild_state IN ('queued', 'running')"
                "           THEN 0 ELSE 1 END) AS priority"
                " FROM embedding_indexes ei"
                " WHERE ei.rebuild_state IN ('queued', 'running')"
                "    OR (ei.is_active AND ei.last_error IS NULL AND EXISTS ("
                "        SELECT 1 FROM source_embeddings se"
                "        WHERE se.index_id = ei.id AND se.work_state = 'pending'))"
                " GROUP BY ei.campaign_id"
                " ORDER BY priority"
            )
        )
        campaign_ids = [row[0] for row in rows.fetchall()]
    processed = 0
    for campaign_id in campaign_ids:
        if _stop.is_set():
            break
        if await process_campaign_once(campaign_id):
            processed += 1
    return processed


def wake_embedding_worker() -> None:
    _wake.set()


async def run_embedding_worker() -> None:
    cfg = embedding_queue.get_rebuild_config()
    while not _stop.is_set():
        try:
            await scan_once()
        except Exception:
            logger.exception("embedding_worker_scan_failed")
        if _stop.is_set():
            break
        try:
            await asyncio.wait_for(_wake.wait(), timeout=cfg.scan_interval_seconds)
        except TimeoutError:
            pass
        _wake.clear()


def start_embedding_worker() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _stop.clear()
    _wake.clear()
    _task = asyncio.create_task(run_embedding_worker())


async def stop_embedding_worker() -> None:
    global _task
    _stop.set()
    _wake.set()
    if _task is not None:
        await asyncio.gather(_task, return_exceptions=True)
        _task = None
