import uuid

import pytest

from app.ai.embedding_config import EmbeddingBatch, legacy_space
from app.memory.recall import RecallSnapshot, embed_recall_query


@pytest.mark.asyncio
async def test_embed_recall_query_sends_action_and_anchor_in_one_batch(monkeypatch) -> None:
    captured: list[str] = []

    async def fake_embed_texts(space, texts, *, user_id):
        captured.extend(texts)
        return EmbeddingBatch(space, 2, ((1.0, 0.0), (0.0, 1.0)))

    monkeypatch.setattr("app.memory.recall.embed_texts", fake_embed_texts)
    snapshot = RecallSnapshot(
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), 2, legacy_space(), ("Lyra",)
    )

    prepared = await embed_recall_query(snapshot, "open the door", "At Thornhaven, with Lyra.")

    assert captured == ["open the door", "At Thornhaven, with Lyra."]
    assert prepared is not None
    assert prepared.vectors == {"action": (1.0, 0.0), "anchor": (0.0, 1.0)}


@pytest.mark.asyncio
async def test_embed_recall_query_returns_none_when_provider_fails(monkeypatch) -> None:
    async def fail(space, texts, *, user_id):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.memory.recall.embed_texts", fail)
    snapshot = RecallSnapshot(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), 2, legacy_space())

    assert await embed_recall_query(snapshot, "act", "anchor") is None
