"""ADR 0018 B — the worker's claim, lease, batch snapshot and vector save.

A claim is a lease on one index row. Every write revalidates the token AND the
lease deadline using the database clock, so a stale-but-not-yet-stolen token
cannot save, renew or activate. Save locks campaign -> index -> source, like the
writers and the cutover, and only updates a row whose text hash still matches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.memory import embedding_lifecycle as lifecycle
from app.memory import embedding_queue
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding

if TYPE_CHECKING:
    from app.ai.embedding_config import (
        EmbeddingBatch,
        EmbeddingRebuildConfig,
        EmbeddingSpace,
    )

_PENDING_ROWS = """
    SELECT se.id, COALESCE(t.summary, mf.content), se.text_hash
    FROM source_embeddings se
    LEFT JOIN turns t ON t.id = se.turn_id
    LEFT JOIN memory_facts mf ON mf.id = se.memory_fact_id
    WHERE se.index_id = :iid AND se.work_state = 'pending'
      AND COALESCE(t.summary, mf.content) IS NOT NULL
    ORDER BY se.created_at, se.id
    LIMIT :limit
"""

_CLAIM_TARGET = """
    UPDATE embedding_indexes
    SET rebuild_state = 'running', claim_token = :tok, claimed_at = now()
    WHERE id = :iid AND campaign_id = :cid AND rebuild_state IN ('queued', 'running')
      AND (claim_token IS NULL OR claimed_at <= now() - make_interval(secs => :ttl))
    RETURNING id
"""

_CLAIM_ACTIVE = """
    UPDATE embedding_indexes
    SET claim_token = :tok, claimed_at = now()
    WHERE id = :iid AND campaign_id = :cid AND is_active AND rebuild_state = 'completed'
      AND last_error IS NULL
      AND (claim_token IS NULL OR claimed_at <= now() - make_interval(secs => :ttl))
    RETURNING id
"""

_LEASE = "claimed_at IS NOT NULL AND claimed_at > now() - make_interval(secs => :ttl)"


@dataclass
class Claim:
    index_id: uuid.UUID
    campaign_id: uuid.UUID
    owner_id: uuid.UUID
    token: uuid.UUID
    kind: Literal["batch", "cutover"]
    provider: str
    model: str
    endpoint_name: str | None
    endpoint_identity: str | None
    pipeline_version: str
    is_active: bool
    row_ids: list[uuid.UUID] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)


def manifest_space(claim: Claim) -> EmbeddingSpace:
    """Build the space from the index manifest, never from the user's profile."""
    from app.ai.embedding_config import (
        LEGACY_DIMENSIONS,
        LEGACY_PIPELINE,
        EmbeddingSpace,
        check_space_contract,
    )

    family: Literal["openai", "google"] = "google" if claim.provider == "google" else "openai"
    requested = LEGACY_DIMENSIONS if claim.pipeline_version == LEGACY_PIPELINE else None
    space = EmbeddingSpace(
        provider=claim.provider,
        model=claim.model,
        api_family=family,
        endpoint_name=claim.endpoint_name,
        endpoint_identity=claim.endpoint_identity,
        pipeline_version=claim.pipeline_version,
        requested_dimensions=requested,
    )
    check_space_contract(space)
    return space


async def claim_work(
    db: AsyncSession, campaign_id: uuid.UUID, cfg: EmbeddingRebuildConfig
) -> Claim | None:
    owner_id = await lifecycle.lock_campaign(db, campaign_id)
    if owner_id is None:
        return None
    indexes = (
        (await db.execute(select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == campaign_id)))
        .scalars()
        .all()
    )
    target = next(
        (index for index in indexes if index.rebuild_state in lifecycle.OPEN_STATES), None
    )
    active = None
    for candidate in indexes:
        if (
            candidate.is_active
            and candidate.last_error is None
            and await _has_pending(db, candidate.id)
        ):
            active = candidate
            break
    index = target or active
    if index is None:
        return None
    token = uuid.uuid4()
    statement = _CLAIM_TARGET if target is not None else _CLAIM_ACTIVE
    claimed = await db.execute(
        text(statement),
        {
            "iid": index.id,
            "cid": campaign_id,
            "tok": token,
            "ttl": cfg.rebuild_claim_ttl_seconds,
        },
    )
    if claimed.first() is None:
        return None
    claim = _claim_from_index(index, owner_id, token)
    await embedding_queue.reconcile_index_sources(db, index)
    await _fill_rows(db, claim, cfg)
    if not claim.row_ids:
        if index.is_active:
            index.claim_token = None
            index.claimed_at = None
            return None
        claim.kind = "cutover"
    return claim


async def load_lease(
    db: AsyncSession, claim: Claim, cfg: EmbeddingRebuildConfig, *, lock: bool
) -> EmbeddingIndex | None:
    statement = select(EmbeddingIndex).where(
        EmbeddingIndex.id == claim.index_id,
        EmbeddingIndex.claim_token == claim.token,
        text("(embedding_indexes.rebuild_state = 'running' OR embedding_indexes.is_active)"),
        text(_LEASE).bindparams(ttl=cfg.rebuild_claim_ttl_seconds),
    )
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def next_batch(db: AsyncSession, claim: Claim, cfg: EmbeddingRebuildConfig) -> Claim | None:
    """Snapshot the next batch under the same lease, or a cutover when a target
    has no work left. Active maintenance releases the lease instead."""
    owner_id = await lifecycle.lock_campaign(db, claim.campaign_id)
    if owner_id is None:
        return None
    index = await load_lease(db, claim, cfg, lock=True)
    if index is None:
        return None
    next_claim = _claim_from_index(index, owner_id, claim.token)
    await embedding_queue.reconcile_index_sources(db, index)
    await _fill_rows(db, next_claim, cfg)
    if next_claim.row_ids:
        return next_claim
    if index.is_active:
        index.claim_token = None
        index.claimed_at = None
        return None
    next_claim.kind = "cutover"
    return next_claim


async def save_vectors(
    db: AsyncSession, claim: Claim, batch: EmbeddingBatch, cfg: EmbeddingRebuildConfig
) -> bool:
    if await lifecycle.lock_campaign(db, claim.campaign_id) is None:
        return False
    index = await load_lease(db, claim, cfg, lock=True)
    if index is None:
        return False
    vectors = list(batch.vectors)
    dimension = batch.dimension
    if len(vectors) != len(claim.row_ids) or dimension is None or dimension <= 0:
        _fail_index(index, "The embedding provider returned a malformed batch.")
        return False
    if index.dimension is not None and index.dimension != dimension:
        _fail_index(index, "The embedding provider changed vector dimensions.")
        return False
    current = await _current_hashes(db, claim.row_ids)
    for row_id, digest, vector in zip(claim.row_ids, claim.hashes, vectors, strict=True):
        if current.get(row_id) != digest:
            continue
        await db.execute(
            update(SourceEmbedding)
            .where(
                SourceEmbedding.id == row_id,
                SourceEmbedding.work_state == EmbeddingWorkState.PENDING,
                SourceEmbedding.text_hash == digest,
            )
            .values(
                embedding=list(vector),
                work_state=EmbeddingWorkState.EMBEDDED,
                last_error=None,
            )
        )
    if index.dimension is None:
        index.dimension = dimension
    index.claimed_at = func.now()
    return True


async def mark_failed(claim: Claim, reason: str, cfg: EmbeddingRebuildConfig) -> None:
    async with dependencies.async_session() as db:
        await lifecycle.lock_campaign(db, claim.campaign_id)
        index = await load_lease(db, claim, cfg, lock=True)
        if index is not None:
            _fail_index(index, reason)
        await db.commit()


async def release_claim(claim: Claim, cfg: EmbeddingRebuildConfig) -> None:
    async with dependencies.async_session() as db:
        await lifecycle.lock_campaign(db, claim.campaign_id)
        index = await load_lease(db, claim, cfg, lock=True)
        if index is not None:
            index.claim_token = None
            index.claimed_at = None
        await db.commit()


def _fail_index(index: EmbeddingIndex, reason: str) -> None:
    if not index.is_active:
        index.rebuild_state = State.FAILED
    index.last_error = reason[:500]
    index.claim_token = None
    index.claimed_at = None


def _claim_from_index(index: EmbeddingIndex, owner_id: uuid.UUID, token: uuid.UUID) -> Claim:
    return Claim(
        index_id=index.id,
        campaign_id=index.campaign_id,
        owner_id=owner_id,
        token=token,
        kind="batch",
        provider=index.provider,
        model=index.model,
        endpoint_name=index.endpoint_name,
        endpoint_identity=index.endpoint_identity,
        pipeline_version=index.pipeline_version,
        is_active=index.is_active,
    )


async def _fill_rows(db: AsyncSession, claim: Claim, cfg: EmbeddingRebuildConfig) -> None:
    rows = await db.execute(text(_PENDING_ROWS), {"iid": claim.index_id, "limit": cfg.batch_size})
    claim.row_ids, claim.texts, claim.hashes = [], [], []
    for row_id, source_text, digest in rows.fetchall():
        claim.row_ids.append(row_id)
        claim.texts.append(source_text)
        claim.hashes.append(digest)


async def _has_pending(db: AsyncSession, index_id: uuid.UUID) -> bool:
    row = await db.execute(
        text(
            "SELECT 1 FROM source_embeddings"
            " WHERE index_id = :iid AND work_state = 'pending' LIMIT 1"
        ),
        {"iid": index_id},
    )
    return row.first() is not None


async def _current_hashes(db: AsyncSession, row_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not row_ids:
        return {}
    statement = text(
        "SELECT se.id, encode(sha256(convert_to(COALESCE(t.summary, mf.content), 'UTF8')), 'hex')"
        " FROM source_embeddings se"
        " LEFT JOIN turns t ON t.id = se.turn_id"
        " LEFT JOIN memory_facts mf ON mf.id = se.memory_fact_id"
        " WHERE se.id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = await db.execute(statement, {"ids": row_ids})
    return {row_id: digest for row_id, digest in rows.fetchall()}
