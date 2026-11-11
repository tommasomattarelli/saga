"""Eval-only accounting wrappers for the supported generation and embedding clients."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from app.ai.embedding_config import EmbeddingPolicy
from app.ai.generation_attempt import single_generation_attempt
from app.ai.providers import embeddings_google, embeddings_openai
from app.ai.providers.base import AIProvider
from app.ai.providers.local import LocalProvider
from app.ai.providers.schemas import AgentResponse
from eval.dialogue.limits import FreeRequestLimiter
from eval.integrated_memory.ledger import IntegratedLedger, LedgerBlockedError

T = TypeVar("T")
_OPENAI_RETRY = embeddings_openai.request_with_finite_retry
_GOOGLE_RETRY = embeddings_google.request_with_finite_retry


class _GuardedGeneration(AIProvider):
    def __init__(
        self, wrapped: LocalProvider, ledger: IntegratedLedger, limiter: FreeRequestLimiter | None
    ) -> None:
        self.wrapped = wrapped
        self.ledger = ledger
        self.limiter = limiter

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        self.ledger.ensure_healthy()
        scope = self.ledger.current_scope
        if scope is None or scope.provider != "openrouter" or scope.model != model:
            raise LedgerBlockedError("generation requires a matching OpenRouter attempt scope")
        if self.limiter is not None:
            await self.limiter.wait(model)
        request = [{"role": "system", "content": system_prompt}, *messages]
        digest = hashlib.sha256(
            json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.ledger.reserve(
            "generation", {"provider": "openrouter", "model": model, "input_hash": digest}, texts=0
        )
        try:
            with single_generation_attempt():
                result = await self.wrapped.generate(
                    system_prompt, messages, model, max_tokens, json_mode
                )
        except asyncio.CancelledError:
            self.ledger.cancel()
            raise
        except BaseException:
            self.ledger.fail()
            raise
        self.ledger.complete()
        return result

    async def _unsupported(self) -> None:
        raise LedgerBlockedError("integrated evaluation supports generation only")

    def stream(
        self, system_prompt: str, messages: list[dict], model: str, max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        async def unsupported() -> AsyncIterator[str]:
            await self._unsupported()
            yield ""

        return unsupported()

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        await self._unsupported()
        raise AssertionError("unsupported generation returned")


def guard_generation(
    provider: LocalProvider,
    ledger: IntegratedLedger,
    *,
    limiter: FreeRequestLimiter | None = None,
) -> AIProvider:
    """Wrap only the OpenRouter LocalProvider path supported by this offline runner."""
    if not isinstance(provider, LocalProvider):
        raise TypeError("integrated evaluation requires LocalProvider backed by OpenRouter")
    if provider.client.base_url.host != "openrouter.ai":
        raise TypeError("integrated evaluation supports OpenRouter generation only")
    return _GuardedGeneration(provider, ledger, limiter)


@contextmanager
def guard_embedding_attempts(
    ledger: IntegratedLedger, *, model: str, provider: str, texts: list[str]
) -> Iterator[None]:
    """Patch adapter retry aliases for one serial eval operation; not concurrency-safe."""
    request_hash = hashlib.sha256(
        json.dumps(texts, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()

    def wrap(original: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        async def guarded(
            *,
            provider: str,
            policy: EmbeddingPolicy,
            call: Callable[[], Awaitable[T]],
            is_transient: Callable[[Exception], bool],
        ) -> T:
            scope = ledger.current_scope
            if scope is None or scope.model != model or scope.provider != provider:
                ledger.latch()
                raise LedgerBlockedError("embedding request requires a matching attempt scope")
            attempts = 0

            async def guarded_call() -> T:
                nonlocal attempts
                attempts += 1
                try:
                    ledger.reserve(
                        "embedding",
                        {
                            "provider": provider,
                            "model": model,
                            "input_hash": request_hash,
                            "space": provider,
                        },
                        texts=len(texts),
                    )
                except LedgerBlockedError:
                    ledger.latch()
                    raise
                try:
                    result = await call()
                except asyncio.CancelledError:
                    ledger.cancel()
                    raise
                except BaseException as exc:
                    retrying = (
                        isinstance(exc, Exception)
                        and is_transient(exc)
                        and attempts <= policy.max_retries
                    )
                    ledger.fail(retrying=retrying)
                    raise
                ledger.complete()
                return result

            try:
                return await original(
                    provider=provider, policy=policy, call=guarded_call, is_transient=is_transient
                )
            except Exception as exc:
                try:
                    ledger.ensure_healthy()
                except LedgerBlockedError as blocked:
                    raise blocked from exc
                raise

        return guarded

    with (
        _patched(embeddings_openai, "request_with_finite_retry", wrap(_OPENAI_RETRY)),
        _patched(embeddings_google, "request_with_finite_retry", wrap(_GOOGLE_RETRY)),
    ):
        yield


@contextmanager
def _patched(module: object, name: str, value: object) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)
