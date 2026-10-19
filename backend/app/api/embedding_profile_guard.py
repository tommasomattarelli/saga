"""Serialization guard for a personal embedding-profile change (ADR 0018 B).

Settings, ensure and retry all take the owner's user row lock first. Holding it
while checking the user's own campaigns means a profile change cannot slip in
between the check and an ensure that creates a job with the superseded profile.
Key and consent updates never pass through here: they stay always possible.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.user import User

_EMBEDDING_FIELDS = (
    "embedding_provider",
    "embedding_model",
    "embedding_local_endpoint",
)


async def guard_embedding_profile_change(
    db: AsyncSession, user: User, fields: dict[str, object]
) -> None:
    if not any(field in fields for field in _EMBEDDING_FIELDS):
        return
    await db.execute(text("SELECT id FROM users WHERE id = :uid FOR UPDATE"), {"uid": user.id})
    open_job = (
        await db.execute(
            select(EmbeddingIndex.id)
            .join(Campaign, Campaign.id == EmbeddingIndex.campaign_id)
            .where(
                Campaign.user_id == user.id,
                EmbeddingIndex.rebuild_state.in_((State.QUEUED, State.RUNNING)),
            )
            .limit(1)
        )
    ).first()
    if open_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cancel your campaigns' in-flight embedding rebuilds before"
                " changing the embedding profile."
            ),
        )
