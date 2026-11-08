"""Builders and provider fakes for the ADR 0018 B rebuild tests.

Provider calls are faked at the single seam in ``app.memory.embedding_queue``;
the database is always the real PostgreSQL test database.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory import embedding_queue
from app.models.campaign import Campaign, Difficulty
from app.models.memory_fact import MemoryFact
from app.models.turn import Turn
from app.models.user import User

DIMENSION = 8


def fake_space(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "provider": "openrouter",
        "model": "openai/text-embedding-3-small",
        "api_family": "openai",
        "endpoint_name": None,
        "endpoint_identity": "https://openrouter.ai/api/v1",
        "pipeline_version": "embed-v1",
        "requested_dimensions": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_rebuild_config(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "batch_size": 32,
        "rebuild_min_interval_seconds": 0,
        "rebuild_concurrency": 1,
        "rebuild_claim_ttl_seconds": 600,
        "scan_interval_seconds": 0,
        "request_timeout_seconds": 30,
        "max_retries": 2,
        "retry_delays_seconds": [1, 3],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_resolved(space: SimpleNamespace, policy: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(space=space, policy=policy, credential=None)


def install_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    space: SimpleNamespace | None = None,
    policy: SimpleNamespace | None = None,
    embed: Any | None = None,
    resolve: Any | None = None,
) -> SimpleNamespace:
    space_value = space or fake_space()
    policy_value = policy or fake_rebuild_config()
    calls: dict[str, Any] = {"embed": 0, "texts": []}

    async def default_resolve(user_id: Any, *, space: Any = None) -> SimpleNamespace:
        return fake_resolved(space_value, policy_value)

    async def default_embed(texts: list[str], resolved: Any) -> SimpleNamespace:
        calls["embed"] += 1
        calls["texts"].append(list(texts))
        vector = [float(calls["embed"])] * DIMENSION
        return SimpleNamespace(vectors=[list(vector) for _ in texts], dimension=DIMENSION)

    monkeypatch.setattr(embedding_queue, "get_rebuild_config", lambda: policy_value)
    monkeypatch.setattr(embedding_queue, "resolve_embedding", resolve or default_resolve)
    monkeypatch.setattr(embedding_queue, "embed_texts_via_provider", embed or default_embed)
    return SimpleNamespace(space=space_value, policy=policy_value, calls=calls)


async def create_user_campaign(
    db: AsyncSession, *, provider: str | None = None, model: str | None = None
) -> tuple[User, Campaign]:
    suffix = uuid.uuid4().hex[:10]
    user = User(
        username=f"u_{suffix}",
        email=f"u_{suffix}@example.com",
        hashed_password="pw",
        is_active=True,
        embedding_provider=provider,
        embedding_model=model,
    )
    db.add(user)
    await db.flush()
    campaign = Campaign(
        user_id=user.id, world_slug="w", name=f"c_{suffix}", difficulty=Difficulty.MEDIUM
    )
    db.add(campaign)
    await db.commit()
    return user, campaign


async def add_turn(db: AsyncSession, campaign: Campaign, number: int, summary: str | None) -> Turn:
    turn = Turn(
        campaign_id=campaign.id,
        turn_number=number,
        player_action="act",
        narration="something happens",
        model_used="test-model",
        summary=summary,
    )
    db.add(turn)
    await db.flush()
    return turn


async def add_fact(db: AsyncSession, campaign: Campaign, number: int, content: str) -> MemoryFact:
    fact = MemoryFact(
        campaign_id=campaign.id,
        turn_number=number,
        entity_name="Entity",
        entity_type="npc",
        content=content,
    )
    db.add(fact)
    await db.flush()
    return fact
