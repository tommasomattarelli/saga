"""Embedding runtime — batch vectors through the resolved user policy (ADR 0018 B).

All runtime calls use batches through a resolved user credential, and the
resolution entry point is the router (short session, never held across network).
"""

import uuid

from app.ai.embedding_config import (
    EmbeddingAdapter,
    EmbeddingBatch,
    EmbeddingSpace,
    ResolvedEmbedding,
    check_space_contract,
)
from app.ai.providers.embeddings_google import GoogleEmbeddingAdapter
from app.ai.providers.embeddings_openai import (
    OpenAICompatEmbeddingAdapter,
    get_openai_compat_adapter,
)
from app.exceptions import ValidationError

# --- NEW runtime (ADR 0018 B) ------------------------------------------------------

_openai_adapters: dict[tuple[str, str | None, str | None], OpenAICompatEmbeddingAdapter] = {}
_google_adapters: dict[str | None, GoogleEmbeddingAdapter] = {}


def get_embedding_adapter(resolved: ResolvedEmbedding) -> EmbeddingAdapter:
    """Cached client per (provider, endpoint identity, credential) — never cross-user."""
    space = resolved.space
    if space.api_family == "google":
        return _google_adapter(resolved)
    return _openai_adapter(resolved)


def _openai_adapter(resolved: ResolvedEmbedding) -> OpenAICompatEmbeddingAdapter:
    cache_key = (
        resolved.space.provider,
        resolved.space.endpoint_identity,
        resolved.credential.key,
    )
    adapter = _openai_adapters.get(cache_key)
    if adapter is None:
        adapter = get_openai_compat_adapter(resolved)
        _openai_adapters[cache_key] = adapter
    return adapter


def _google_adapter(resolved: ResolvedEmbedding) -> GoogleEmbeddingAdapter:
    cache_key = resolved.credential.key
    adapter = _google_adapters.get(cache_key)
    if adapter is None:
        adapter = GoogleEmbeddingAdapter(api_key=resolved.credential.key, policy=resolved.policy)
        _google_adapters[cache_key] = adapter
    return adapter


def reset_adapter_cache() -> None:
    """Isolation hook for tests only — production code never resets this cache."""
    _openai_adapters.clear()
    _google_adapters.clear()


def _validate_texts(texts: list[str]) -> None:
    if not texts:
        raise ValidationError("No embedding input provided.")
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("An embedding input is empty or not a string.")


def _check_pinned_dimension(batch: EmbeddingBatch, requested: int | None, provider: str) -> None:
    from app.exceptions import AIProviderError

    if requested is not None and batch.dimension != requested:
        raise AIProviderError(
            provider,
            f"the provider returned dimension {batch.dimension} but the index pins {requested}",
        )


async def embed_batch(texts: list[str], resolved: ResolvedEmbedding) -> EmbeddingBatch:
    """Ordered vectors 1:1 with input; space identity travels with the batch."""
    check_space_contract(resolved.space)
    _validate_texts(texts)
    adapter = get_embedding_adapter(resolved)
    dimension, vectors = await adapter.embed(
        resolved.space.model, texts, dimensions=resolved.space.requested_dimensions
    )
    batch = EmbeddingBatch(
        space=resolved.space,
        dimension=dimension,
        vectors=tuple(tuple(vector) for vector in vectors),
    )
    _check_pinned_dimension(batch, resolved.space.requested_dimensions, resolved.space.provider)
    return batch


async def embed_texts(
    space: EmbeddingSpace, texts: list[str], *, user_id: uuid.UUID | str
) -> EmbeddingBatch:
    """One provider request: resolve credentials in a short session, then network."""
    from app.ai.router import get_user_embedding

    resolved = await get_user_embedding(user_id, space=space)
    return await embed_batch(texts, resolved)


async def embed_query_for_index(
    space: EmbeddingSpace, text: str, *, user_id: uuid.UUID | str
) -> EmbeddingBatch:
    """The recall-side query wrapper: the manifest space is validated, never swapped."""
    return await embed_texts(space, [text], user_id=user_id)
