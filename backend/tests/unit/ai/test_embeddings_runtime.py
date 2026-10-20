"""Runtime tests for the batch embedding surface (no provider calls)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.embedding_config import (
    EmbeddingCredential,
    EmbeddingPolicy,
    ResolvedEmbedding,
    build_space,
    legacy_space,
    local_space,
)
from app.ai.embeddings import (
    embed_batch,
    embed_query_for_index,
    embed_texts,
    get_embedding_adapter,
    reset_adapter_cache,
)
from app.exceptions import AIProviderError, ValidationError


def policy(max_retries: int = 2, delays: tuple[int, ...] = (1, 3)) -> EmbeddingPolicy:
    return EmbeddingPolicy(
        batch_size=32,
        rebuild_min_interval_seconds=1,
        rebuild_concurrency=1,
        rebuild_claim_ttl_seconds=600,
        request_timeout_seconds=30,
        max_retries=max_retries,
        retry_delays_seconds=delays,
    )


def resolved(space=None, *, key: str | None = "test-key", source: str = "personal"):
    return ResolvedEmbedding(
        space=space or build_space("openrouter", "openai/mistral-embed"),
        credential=EmbeddingCredential(key=key, source=source),
        policy=policy(),
    )


class FakeAdapter:
    def __init__(self, dimension: int = 2, vectors: list[list[float]] | None = None) -> None:
        self.dimension = dimension
        self.vectors = vectors
        self.calls: list[tuple[str, list[str], int | None]] = []

    async def embed(self, model: str, texts: list[str], *, dimensions=None):
        self.calls.append((model, list(texts), dimensions))
        vectors = self.vectors or [[0.1] * self.dimension for _ in texts]
        return self.dimension, vectors


class TestEmbedBatch:
    async def test_rejects_empty_and_blank_inputs_before_any_call(self):
        fake = FakeAdapter()
        with patch("app.ai.embeddings.get_embedding_adapter", return_value=fake):
            with pytest.raises(ValidationError):
                await embed_batch([], resolved())
            with pytest.raises(ValidationError):
                await embed_batch(["   "], resolved())
        assert fake.calls == []

    async def test_passes_texts_in_order_and_carries_the_space(self):
        fake = FakeAdapter()
        with patch("app.ai.embeddings.get_embedding_adapter", return_value=fake):
            batch = await embed_batch(["first", "second"], resolved())
        assert fake.calls == [("openai/mistral-embed", ["first", "second"], None)]
        assert batch.space is not None
        assert batch.space.provider == "openrouter"
        assert batch.dimension == 2
        assert batch.vectors == ((0.1, 0.1), (0.1, 0.1))

    async def test_legacy_space_requests_384_and_checks_the_pinned_dimension(self):
        fake = FakeAdapter(dimension=384, vectors=[[0.1] * 384])
        with patch("app.ai.embeddings.get_embedding_adapter", return_value=fake):
            batch = await embed_batch(["q"], resolved(legacy_space(), key="openai-key"))
        assert fake.calls[0][2] == 384
        assert batch.dimension == 384

        wrong = FakeAdapter(dimension=1536)
        with (
            patch("app.ai.embeddings.get_embedding_adapter", return_value=wrong),
            pytest.raises(AIProviderError, match="pins 384"),
        ):
            await embed_batch(["q"], resolved(legacy_space(), key="openai-key"))

    async def test_space_is_revalidated_against_today_policy_before_the_network(self):
        stale = local_space("ollama", "nomic-embed-text")
        moved = replace(stale, endpoint_identity="http://10.0.0.9:11434/v1")
        fake = FakeAdapter()
        with (
            patch("app.ai.embeddings.get_embedding_adapter", return_value=fake) as factory,
            pytest.raises(ValidationError, match="no longer authorized"),
        ):
            await embed_batch(["t"], resolved(moved, key=None, source="not_required"))
        assert factory.call_count == 0


class TestAdapterCache:
    @pytest.fixture(autouse=True)
    def clean(self):
        reset_adapter_cache()
        yield
        reset_adapter_cache()

    def test_same_credential_and_endpoint_share_the_client(self):
        first = get_embedding_adapter(resolved(key="same-key"))
        second = get_embedding_adapter(resolved(key="same-key"))
        assert first is second

    def test_different_credentials_never_share_a_client(self):
        one = get_embedding_adapter(resolved(key="user-one-key"))
        two = get_embedding_adapter(resolved(key="user-two-key"))
        assert one is not two

    def test_different_endpoint_identity_never_shares_a_client(self):
        openrouter = get_embedding_adapter(resolved(key="same-key"))
        openai = get_embedding_adapter(
            resolved(build_space("openai", "text-embedding-3-small"), key="same-key")
        )
        assert openrouter is not openai


class TestWrappers:
    async def test_embed_texts_resolves_then_embeds_without_swapping_the_space(self):
        space = build_space("openrouter", "openai/mistral-embed")
        fake = FakeAdapter()
        with (
            patch(
                "app.ai.router.get_user_embedding", new=AsyncMock(return_value=resolved(space))
            ) as resolve,
            patch("app.ai.embeddings.get_embedding_adapter", return_value=fake),
        ):
            batch = await embed_texts(space, ["a", "b"], user_id="user-1")
        resolve.assert_awaited_once_with("user-1", space=space)
        assert fake.calls == [("openai/mistral-embed", ["a", "b"], None)]
        assert batch.dimension == 2

    async def test_embed_query_for_index_uses_one_text(self):
        space = legacy_space()
        fake = FakeAdapter(dimension=384, vectors=[[0.5] * 384])
        with (
            patch(
                "app.ai.router.get_user_embedding",
                new=AsyncMock(return_value=resolved(space, key="openai-key")),
            ),
            patch("app.ai.embeddings.get_embedding_adapter", return_value=fake),
        ):
            batch = await embed_query_for_index(space, "the inn is closed", user_id="user-1")
        assert fake.calls == [("text-embedding-3-small", ["the inn is closed"], 384)]
        assert batch.space.pipeline_version == "embed-v1-legacy"
        assert batch.dimension == 384
