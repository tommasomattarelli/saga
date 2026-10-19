"""Embedding response validation and the only retry policy embeddings use (std 13)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from app.ai.exceptions import PROVIDER_SDK_ERRORS, provider_failure_message
from app.exceptions import AIProviderError

if TYPE_CHECKING:
    from app.ai.embedding_config import EmbeddingPolicy

TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
IN_BAND_REJECTION = "the provider rejected the embedding request; check your embedding settings."


def provider_error(provider: str, exc: Exception) -> AIProviderError:
    """Short sanitized provider failure: no URL, no key, no upstream payload."""
    if isinstance(exc, PROVIDER_SDK_ERRORS):
        return AIProviderError(provider, provider_failure_message(exc))
    return AIProviderError(
        provider, "the provider request failed; check your embedding settings and try again later."
    )


def has_in_band_error(response: object) -> bool:
    """A 200 can still carry an error (OpenRouter); its payload is never surfaced."""
    if getattr(response, "error", None):
        return True
    extra = getattr(response, "model_extra", None)
    return bool(extra.get("error")) if isinstance(extra, dict) else False


def validate_embedding_entries(
    entries: list[tuple[int, list[float]]], count: int, provider: str
) -> list[list[float]]:
    """1:1 ordered vectors: index integrity, mixed dimensions, finiteness, cosine usability."""
    if len(entries) != count:
        raise AIProviderError(
            provider,
            f"the provider returned {len(entries)} embedding entries for {count} inputs",
        )
    by_index: dict[int, list[float]] = {}
    for index, vector in entries:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < count:
            raise AIProviderError(
                provider, "the provider returned an out-of-range embedding index"
            )
        if index in by_index:
            raise AIProviderError(provider, "the provider returned a duplicate embedding index")
        by_index[index] = list(vector)
    ordered = [by_index[position] for position in range(count)]
    dimensions = {len(vector) for vector in ordered}
    if len(dimensions) != 1:
        raise AIProviderError(provider, "the provider returned mixed embedding dimensions")
    if ordered[0].__len__() == 0:
        raise AIProviderError(provider, "the provider returned an empty embedding")
    for vector in ordered:
        if not all(math.isfinite(value) for value in vector):
            raise AIProviderError(provider, "the provider returned a non-finite embedding value")
        if all(value == 0.0 for value in vector):
            raise AIProviderError(
                provider, "the provider returned a zero vector; cosine distance is unusable"
            )
    return ordered


async def request_with_finite_retry[T](
    *,
    provider: str,
    policy: EmbeddingPolicy,
    call: Callable[[], Awaitable[T]],
    is_transient: Callable[[Exception], bool],
) -> T:
    """The single retry policy: max_retries extra attempts after the first call.

    Auth/quota/rate-limit errors return after the FIRST attempt — they never
    retry, and never against another key or provider. Delay table is finite
    ([1,3]s); an exhausted table or a non-transient error surfaces sanitized.
    """
    last_transient: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            return await call()
        except Exception as exc:
            if not is_transient(exc):
                raise provider_error(provider, exc) from exc
            last_transient = exc
            if attempt < policy.max_retries:
                delay = policy.retry_delays_seconds[
                    min(attempt, len(policy.retry_delays_seconds) - 1)
                ]
                await asyncio.sleep(delay)
    raise provider_error(provider, last_transient or RuntimeError())
