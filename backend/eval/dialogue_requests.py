import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, replace

from dialogue_affinity import provider_with_session
from dialogue_limits import FreeRequestLimiter
from ledger import Attempt, BudgetExhaustedError, RequestLedger
from live_calls import EvaluationPausedError
from provider_trace import ProviderTrace

from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse
from app.ai.providers.usage import current_correlation


class SuiteProvider(AIProvider):
    def __init__(
        self,
        provider: AIProvider,
        ledger: RequestLedger,
        *,
        key: str,
        case: str,
        model: str,
        run: int,
        commit: str,
        ceiling: int,
        checkpoint: str = "pr2-final",
        limiter: FreeRequestLimiter | None = None,
        stop: asyncio.Event | None = None,
        session_id: str | None = None,
    ) -> None:
        self.provider = provider_with_session(provider, session_id)
        self.request_headers = {"x-session-id": session_id} if session_id is not None else {}
        self.ledger = ledger
        self.key = key
        self.case = case
        self.model = model
        self.run = run
        self.commit = commit
        self.ceiling = ceiling
        self.checkpoint = checkpoint
        self.limiter = limiter
        self.stop = stop
        self.count = 0
        self.paused = False
        self.exhausted = False
        self.errors = False

    async def _call[T](
        self, kind: str, request: dict, invoke: Callable[[ProviderTrace], Awaitable[T]]
    ) -> T:
        if self.stop is not None and self.stop.is_set():
            self.paused = True
            raise EvaluationPausedError("Evaluation paused before the next request.")
        wait_seconds = await self.limiter.wait(self.model) if self.limiter else 0.0
        if self.stop is not None and self.stop.is_set():
            self.paused = True
            raise EvaluationPausedError("Evaluation paused before the next request.")
        if self.count >= self.ceiling:
            self.exhausted = True
            raise BudgetExhaustedError("The foreground trial request cap was reached.")
        fingerprint = (
            {"body": request, "headers": self.request_headers} if self.request_headers else request
        )
        attempt = Attempt(
            key=f"{self.key}|request-{self.count}",
            scenario=self.case,
            probe=f"{self.case}:{kind}",
            run=self.run,
            checkpoint=self.checkpoint,
            model=self.model,
            commit=self.commit,
            request=request,
            request_headers=dict(self.request_headers),
            request_hash=hashlib.sha256(
                json.dumps(fingerprint, sort_keys=True).encode()
            ).hexdigest(),
            correlation=asdict(replace(current_correlation(), role=kind)),
            rate_limit_wait_seconds=wait_seconds,
        )
        try:
            self.ledger.reserve(attempt)
        except BudgetExhaustedError:
            self.exhausted = True
            raise
        self.count += 1
        trace = ProviderTrace(self.provider)
        started = time.monotonic()
        try:
            result = await invoke(trace)
            attempt.status = "ok"
            return result
        except Exception as exc:
            self.errors = True
            code = getattr(exc, "status_code", None)
            self.paused = self.paused or code == 429 or "(code 429)" in str(exc)
            if self.paused and self.stop is not None:
                self.stop.set()
            attempt.status = "error"
            attempt.error = f"Provider request failed{f' (HTTP {code})' if code else ''}."
            attempt.failed = ["provider-error"]
            raise
        finally:
            attempt.request = trace.request or request
            attempt.response = trace.response
            attempt.usage = [asdict(item) for item in trace.usage]
            attempt.seconds = time.monotonic() - started
            if attempt.status != "reserved":
                self.ledger.record(attempt)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        request = dict(
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return await self._call("actor", request, lambda trace: trace.generate(**request))

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        request = dict(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
        )
        return await self._call("dm", request, lambda trace: trace.generate_with_tools(**request))

    def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Dialogue evaluation uses non-streaming requests.")
