"""OpenAI-compatible embedding adapter: OpenAI, OpenRouter, local endpoints.

Batch input is always an ARRAY of texts; the response maps back by `index`
(ADR 0018 B4). The SDK's internal retries are force-disabled here: the
`request_with_finite_retry` policy is the only retry path, so a transient
failure takes at most max_retries+1 HTTP attempts, never 3x3 nested attempts.
"""

from __future__ import annotations

from collections.abc import Awaitable

import openai
from openai.types import CreateEmbeddingResponse

from app.ai.embedding_config import (
    OPENAI_MAX_EMBEDDING_INPUTS,
    EmbeddingPolicy,
    ResolvedEmbedding,
)
from app.ai.embedding_validation import (
    IN_BAND_REJECTION,
    has_in_band_error,
    request_with_finite_retry,
    validate_embedding_entries,
)
from app.exceptions import AIProviderError, ValidationError


def _transient_openai(exc: Exception) -> bool:
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in (500, 502, 503, 504)
    return isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError))


class OpenAICompatEmbeddingAdapter:
    def __init__(
        self, *, provider: str, api_key: str | None, base_url: str | None, policy: EmbeddingPolicy
    ):
        self.provider = provider
        self.policy = policy
        # max_retries=0: at the transport boundary this adapter alone decides retries.
        self.client = openai.AsyncOpenAI(
            api_key=api_key or "local",
            base_url=base_url,
            max_retries=0,
        )

    async def embed(
        self, model: str, texts: list[str], *, dimensions: int | None = None
    ) -> tuple[int, list[list[float]]]:
        if len(texts) > OPENAI_MAX_EMBEDDING_INPUTS:
            raise ValidationError(
                f"OpenAI accepts at most {OPENAI_MAX_EMBEDDING_INPUTS} embedding inputs per request."
            )

        def call() -> Awaitable[CreateEmbeddingResponse]:
            if dimensions is None:
                return self.client.embeddings.create(
                    model=model,
                    input=list(texts),
                    timeout=self.policy.request_timeout_seconds,
                )
            return self.client.embeddings.create(
                model=model,
                input=list(texts),
                dimensions=dimensions,
                timeout=self.policy.request_timeout_seconds,
            )

        response = await request_with_finite_retry(
            provider=self.provider, policy=self.policy, call=call, is_transient=_transient_openai
        )
        if has_in_band_error(response):
            raise AIProviderError(self.provider, IN_BAND_REJECTION)
        data = getattr(response, "data", None) or []
        entries = [(item.index, list(item.embedding)) for item in data]
        ordered = validate_embedding_entries(entries, len(texts), self.provider)
        return len(ordered[0]), ordered


def get_openai_compat_adapter(resolved: ResolvedEmbedding) -> OpenAICompatEmbeddingAdapter:
    return OpenAICompatEmbeddingAdapter(
        provider=resolved.space.provider,
        api_key=resolved.credential.key,
        base_url=resolved.space.endpoint_identity,
        policy=resolved.policy,
    )
