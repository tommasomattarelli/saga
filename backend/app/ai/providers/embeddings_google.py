"""Google native embedding batch — one independent content per text (ADR 0018 B4).

`contents` is ALWAYS one Content object per text with a single text part: the
docs-level pitfall this guards is a list that aggregates every text into a
single vector. The genai SDK retry options are forced to one attempt — the
`request_with_finite_retry` policy is the only retry path, so a transient
failure takes at most max_retries+1 HTTP attempts per batch.
"""

from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from app.ai.embedding_config import EmbeddingPolicy
from app.ai.embedding_validation import request_with_finite_retry, validate_embedding_entries


def _transient_google(exc: Exception) -> bool:
    from google.genai.errors import APIError

    return isinstance(exc, APIError) and exc.code in (500, 502, 503, 504)


class GoogleEmbeddingAdapter:
    def __init__(self, *, api_key: str | None, policy: EmbeddingPolicy) -> None:
        self.policy = policy
        # attempts=1: the SDK itself never retries; only our finite policy does.
        self.client = genai.Client(
            api_key=api_key or "none",
            http_options=genai_types.HttpOptions(
                timeout=int(policy.request_timeout_seconds * 1000),
                retry_options=genai_types.HttpRetryOptions(attempts=1),
            ),
        )

    async def embed(
        self, model: str, texts: list[str], *, dimensions: int | None = None
    ) -> tuple[int, list[list[float]]]:
        # `dimensions` is accepted for a uniform runtime interface and NEVER sent:
        # check_space_contract rejects any space asking Google for explicit dims.
        contents = [genai_types.Content(parts=[genai_types.Part(text=text)]) for text in texts]
        response = await request_with_finite_retry(
            provider="google",
            policy=self.policy,
            call=lambda: self.client.aio.models.embed_content(model=model, contents=contents),
            is_transient=_transient_google,
        )
        embeddings = list(getattr(response, "embeddings", None) or [])
        entries = [
            (position, list(getattr(embedding, "values", None) or []))
            for position, embedding in enumerate(embeddings)
        ]
        ordered = validate_embedding_entries(entries, len(texts), "google")
        return len(ordered[0]), ordered
