"""Transport-boundary tests for the embedding adapters (no provider calls).

The openai cases patch the SDK's `AsyncEmbeddings.create` (the HTTP boundary)
and count REAL attempt invocations; the google cases fake `genai.Client` at
construction and inspect the exact batch payload. Attempt count, retries,
sanitization and payload shape are asserted at the boundary, not on a mocked
wrapper that could hide nested SDK retries.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest

from app.ai.embedding_config import EmbeddingPolicy, build_space
from app.ai.providers.embeddings_google import GoogleEmbeddingAdapter
from app.ai.providers.embeddings_openai import OpenAICompatEmbeddingAdapter
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


def openai_response(entries: list[tuple[int, list[float]]]):
    data = [SimpleNamespace(index=index, embedding=vector) for index, vector in entries]
    return SimpleNamespace(data=data, model_extra=None)


def status_error(code: int) -> openai.APIStatusError:
    return openai.APIStatusError(
        "private-provider-payload",
        response=httpx.Response(
            code, request=httpx.Request("POST", "https://provider.test/private")
        ),
        body=None,
    )


def adapter(provider: str = "openrouter", **kwargs) -> OpenAICompatEmbeddingAdapter:
    base_url = kwargs.pop("base_url", None) or build_space(provider, "m").endpoint_identity
    return OpenAICompatEmbeddingAdapter(
        provider=provider,
        api_key=kwargs.pop("api_key", "test-key"),
        base_url=base_url,
        policy=kwargs.pop("policy", policy()),
    )


class TestOpenAICompatAdapter:
    async def test_input_is_always_an_array(self):
        with patch(
            "openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()
        ) as create:
            create.return_value = openai_response([(0, [0.1])])
            dimension, vectors = await adapter().embed("m", ["one text"], dimensions=None)
        kwargs = create.call_args.kwargs
        assert kwargs["input"] == ["one text"]
        assert kwargs["model"] == "m"
        assert "dimensions" not in kwargs
        assert kwargs["timeout"] == 30
        assert dimension == 1

    async def test_legacy_request_sends_dimensions_384(self):
        with (
            patch("openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()) as create,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            create.return_value = openai_response([(0, [0.1] * 384), (1, [0.2] * 384)])
            _, vectors = await adapter().embed(
                "text-embedding-3-small", ["a", "b"], dimensions=384
            )
        kwargs = create.call_args.kwargs
        assert kwargs["dimensions"] == 384
        assert kwargs["input"] == ["a", "b"]
        assert len(vectors) == 2

    async def test_results_map_back_by_index_not_by_position(self):
        with (
            patch("openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()) as create,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            create.return_value = openai_response([(1, [0.3, 0.4]), (0, [0.1, 0.2])])
            _, vectors = await adapter().embed("m", ["a", "b"])
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]

    async def test_validation_rejects_index_integrity_failures(self):
        cases = [
            openai_response([(0, [0.1]), (0, [0.2])]),
            openai_response([(0, [0.1])]),  # missing one input
            openai_response([(0, [0.1]), (1, [0.2]), (2, [0.3])]),
        ]
        for payload in cases:
            with (
                patch(
                    "openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()
                ) as create,
                patch("asyncio.sleep", new=AsyncMock()),
            ):
                create.side_effect = None
                create.return_value = payload
                with pytest.raises(AIProviderError):
                    await adapter().embed("m", ["a", "b"])

    async def test_validation_rejects_unusable_vectors(self):
        bad_payloads = [
            openai_response([(0, [0.1, float("nan")]), (1, [0.1, 0.2])]),
            openai_response([(0, [0.0, 0.0]), (1, [0.1, 0.2])]),
            openai_response([(0, [0.1]), (1, [0.2, 0.3])]),
            openai_response([(0, []), (1, [0.2])]),
        ]
        for payload in bad_payloads:
            with (
                patch(
                    "openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()
                ) as create,
                patch("asyncio.sleep", new=AsyncMock()),
            ):
                create.return_value = payload
                with pytest.raises(AIProviderError):
                    await adapter().embed("m", ["a", "b"])

    async def test_inband_200_error_payload_is_never_forwarded(self):
        inband = SimpleNamespace(
            data=None,
            model_extra={
                "error": {
                    "message": (
                        "sk-live-SECRET at https://api.openai.com/v1/embeddings "
                        "/srv/app/trace.py line 42"
                    ),
                    "code": 502,
                }
            },
        )
        with patch(
            "openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()
        ) as create:
            create.return_value = inband
            with pytest.raises(AIProviderError) as error:
                await adapter().embed("m", ["a"])
        text = str(error.value)
        for marker in ("sk-live-SECRET", "https://api.openai.com", "/srv/app", "line 42", "502"):
            assert marker not in text
        assert "rejected" in text

    async def test_sdk_internal_retries_are_disabled(self):
        client = adapter().client
        assert client.max_retries == 0

    @pytest.mark.asyncio
    async def test_transient_errors_retry_within_the_finite_policy(self):
        attempts: list[str] = []

        async def flaky(*args, **kwargs):
            attempts.append("call")
            if len(attempts) < 3:
                raise openai.APIConnectionError(
                    request=httpx.Request("POST", "https://provider.test/private")
                )
            return openai_response([(0, [0.1, 0.2])])

        with (
            patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=flaky),
            patch("app.ai.embedding_validation.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            built = adapter()
            assert built.client.max_retries == 0  # nested SDK retries cannot multiply this count
            _, vectors = await built.embed("m", ["a"])
        assert len(attempts) == 3  # 1 + max_retries, at the HTTP boundary
        assert [call.args[0] for call in sleep.await_args_list] == [1, 3]
        assert vectors == [[0.1, 0.2]]

    @pytest.mark.asyncio
    async def test_auth_and_quota_never_retry_and_never_leak(self):
        for code, keyword in ((401, "key"), (403, "denied"), (429, "rate limit or quota")):
            attempts: list[str] = []

            async def reject(*args, _code=code, _attempts=attempts, **kwargs):
                _attempts.append("call")
                raise status_error(_code)

            with (
                patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=reject),
                patch("app.ai.embedding_validation.asyncio.sleep", new=AsyncMock()) as sleep,
                pytest.raises(AIProviderError) as error,
            ):
                await adapter().embed("m", ["a"], dimensions=384)
            assert len(attempts) == 1
            assert sleep.await_count == 0
            assert "provider.test" not in str(error.value)
            assert "private-provider-payload" not in str(error.value)
            assert keyword in str(error.value)

    async def test_oversize_batch_is_refused_without_contacting_anyone(self):
        with (
            patch("openai.resources.embeddings.AsyncEmbeddings.create", new=AsyncMock()) as create,
            pytest.raises(ValidationError),
        ):
            await adapter().embed("m", ["t"] * 2049)
        assert create.await_count == 0


class TestGoogleAdapter:
    def fake_client(self, recordings: dict):
        embed = AsyncMock()

        class FakeAsyncModels:
            def __init__(self) -> None:
                self.embed_content = embed

        class FakeAiO:
            def __init__(self) -> None:
                self.models = FakeAsyncModels()

        class FakeClient:
            def __init__(self, *, api_key, http_options) -> None:
                recordings["api_key"] = api_key
                recordings["http_options"] = http_options
                self.aio = FakeAiO()

        return FakeClient, embed

    async def test_batch_sends_one_independent_content_per_text(self):
        recordings: dict = {}
        fake_client, embed = self.fake_client(recordings)
        with patch("app.ai.providers.embeddings_google.genai.Client", new=fake_client):
            google_adapter = GoogleEmbeddingAdapter(api_key="test-google", policy=policy())
            embed.return_value = SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[0.1, 0.2]),
                    SimpleNamespace(values=[0.3, 0.4]),
                ]
            )
            dimension, vectors = await google_adapter.embed(
                "gemini-embedding-001", ["one fish", "two fish"]
            )
        assert dimension == 2
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]
        contents = embed.call_args.kwargs["contents"]
        assert len(contents) == 2
        for content, text in zip(contents, ["one fish", "two fish"], strict=True):
            parts = list(content.parts)
            assert len(parts) == 1
            assert parts[0].text == text
        assert recordings["api_key"] == "test-google"
        assert recordings["http_options"].timeout == 30000
        assert recordings["http_options"].retry_options.attempts == 1

    async def test_never_sends_an_explicit_dimensions_parameter(self):
        recordings: dict = {}
        fake_client, embed = self.fake_client(recordings)
        with patch("app.ai.providers.embeddings_google.genai.Client", new=fake_client):
            google_adapter = GoogleEmbeddingAdapter(api_key="test-google", policy=policy())
            embed.return_value = SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])
            await google_adapter.embed("gemini", ["a"], dimensions=384)
        assert "dimensions" not in embed.call_args.kwargs

    async def test_result_count_is_enforced(self):
        for response in (
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])]),
            SimpleNamespace(
                embeddings=[
                    SimpleNamespace(values=[0.1, 0.2]),
                    SimpleNamespace(values=[]),
                ]
            ),
            SimpleNamespace(embeddings=None),
        ):
            recordings: dict = {}
            fake_client, embed = self.fake_client(recordings)
            with patch("app.ai.providers.embeddings_google.genai.Client", new=fake_client):
                google_adapter = GoogleEmbeddingAdapter(api_key="k", policy=policy())
                embed.return_value = response
                with pytest.raises(AIProviderError):
                    await google_adapter.embed("gemini", ["a", "b"])

    async def test_transient_google_errors_retry_within_the_policy(self):
        recordings: dict = {}
        fake_client, embed = self.fake_client(recordings)
        attempts = []

        async def flaky(*args, **kwargs):
            attempts.append("call")
            if len(attempts) < 3:
                raise _google_error(503)
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])

        with (
            patch("app.ai.providers.embeddings_google.genai.Client", new=fake_client),
            patch("app.ai.embedding_validation.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            google_adapter = GoogleEmbeddingAdapter(api_key="k", policy=policy())
            embed.side_effect = flaky
            _, vectors = await google_adapter.embed("gemini", ["a"])
        assert len(attempts) == 3
        assert [call.args[0] for call in sleep.await_args_list] == [1, 3]
        assert vectors == [[0.1, 0.2]]


def _google_error(code: int):
    from google.genai.errors import APIError

    return APIError(code, {"error": {"message": "private-upstream"}})
