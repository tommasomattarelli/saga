import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, replace

from ledger import Attempt, BudgetExhaustedError, RequestLedger
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
    ) -> None:
        self.provider = provider
        self.ledger = ledger
        self.key = key
        self.case = case
        self.model = model
        self.run = run
        self.commit = commit
        self.ceiling = ceiling
        self.checkpoint = checkpoint
        self.count = 0
        self.paused = False
        self.exhausted = False
        self.errors = False

    async def _call[T](
        self, kind: str, request: dict, invoke: Callable[[ProviderTrace], Awaitable[T]]
    ) -> T:
        if self.count >= self.ceiling:
            self.exhausted = True
            raise BudgetExhaustedError("The foreground trial request cap was reached.")
        attempt = Attempt(
            key=f"{self.key}|request-{self.count}",
            scenario=self.case,
            probe=f"{self.case}:{kind}",
            run=self.run,
            checkpoint=self.checkpoint,
            model=self.model,
            commit=self.commit,
            request=request,
            correlation=asdict(replace(current_correlation(), role=kind)),
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
            attempt.status = "error"
            attempt.error = f"Provider request failed{f' (HTTP {code})' if code else ''}."
            attempt.failed = ["provider-error"]
            raise
        finally:
            attempt.request = trace.request or request
            attempt.response = trace.response
            attempt.usage = [asdict(item) for item in trace.usage]
            attempt.seconds = time.monotonic() - started
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
