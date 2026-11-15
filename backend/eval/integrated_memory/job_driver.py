from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from time import monotonic
from typing import Literal, cast
from uuid import UUID

import httpx
from sqlalchemy import select

from app import dependencies
from app.ai.generation_attempt import single_generation_attempt
from app.ai.generation_context import Generation, resolve_generation_context
from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import GenerationProvider
from app.ai.generation_execution_ledger import (
    InMemoryGenerationLedger,
)
from app.ai.providers.base import AIProvider
from app.ai.providers.local import LocalProvider
from app.ai.router import ModelConfig, get_generation_recovery_policy
from app.exceptions import ValidationError
from app.memory import job_execution
from app.memory.batch_input import load_batch_input
from app.memory.generation_receipts import decode_receipt
from app.memory.job_claims import JobClaim
from app.memory.job_scheduler import coordinate_memory
from app.memory.producer_prompts import PreparedMemoryRequest
from app.memory.producers import MemoryGeneration, execute_memory_generation
from app.models.campaign import Campaign
from app.models.memory_generation import MemoryGeneration as PersistedMemoryGeneration
from app.models.memory_job import MemoryJob
from eval.dialogue.limits import FreeRequestLimiter
from eval.integrated_memory.evidence_io import append_json, provider_evidence
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger, LedgerBlockedError
from eval.integrated_memory.plan import IntegratedPlan
from eval.support.dialogue_affinity import session_id_for_model
from eval.support.provider_trace import ProviderTrace, generation_request_evidence

GenerationResolver = Callable[[UUID], Awaitable[Generation]]


class _ObservedSend:
    def __init__(
        self,
        scope: AttemptScope,
        trace: ProviderTrace,
        elapsed: float,
        session_affinity: str | None,
    ) -> None:
        self.scope = scope
        self.trace = trace
        self.elapsed = elapsed
        self.session_affinity = session_affinity


def _client_session_id(provider: LocalProvider) -> str | None:
    value = provider.client.default_headers.get("x-session-id")
    return value if isinstance(value, str) else None


@contextmanager
def _capture_actual_session_id(provider: LocalProvider) -> Iterator[dict[str, str | None]]:
    client = cast(httpx.AsyncClient, provider.client._client)
    actual: dict[str, str | None] = {"value": None}

    async def capture(request: httpx.Request) -> None:
        actual["value"] = request.headers.get("x-session-id")

    hooks = client.event_hooks["request"]
    hooks.append(capture)
    try:
        yield actual
    finally:
        hooks.remove(capture)


class _EvalGenerationProvider:
    def __init__(
        self,
        provider: LocalProvider,
        ledger: IntegratedLedger,
        limiter: FreeRequestLimiter | None,
        *,
        scope_for: Callable[[GenerationRequest], AttemptScope] | None = None,
        inputs_path: Path | None = None,
    ) -> None:
        self.provider = provider
        self.ledger = ledger
        self.limiter = limiter
        self.scope_for = scope_for
        self.inputs_path = inputs_path
        self.observed: dict[tuple[str, int], _ObservedSend] = {}
        self.counts: dict[str, int] = {}

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        scope = self.scope_for(request) if self.scope_for else self.ledger.current_scope
        if scope is None:
            raise LedgerBlockedError("integrated generation requires an active attempt scope")
        context = self.ledger.scope(scope) if self.scope_for else nullcontext()
        with context:
            self.ledger.ensure_healthy()
            self.ledger.require_scope(provider="openrouter", model=request.model)
            if _client_session_id(self.provider) != request.session_affinity:
                raise ValidationError(
                    "Integrated request affinity differs from the provider header."
                )
            if self.limiter is not None:
                await self.limiter.wait(request.model)
            request_hash = hashlib.sha256(request.snapshot_json.encode()).hexdigest()
            self.ledger.reserve(
                "generation",
                {"provider": request.provider, "model": request.model, "input_hash": request_hash},
                texts=0,
            )
            trace = ProviderTrace(self.provider, role=f"memory_{request.role}")
            number = self.counts.get(request.role, 0) + 1
            self.counts[request.role] = number
            started = monotonic()
            with _capture_actual_session_id(self.provider) as actual_header:
                try:
                    with single_generation_attempt():
                        receipt = await trace.send(request)
                except asyncio.CancelledError:
                    self.ledger.cancel()
                    raise
                except BaseException:
                    self.ledger.fail()
                    raise
                else:
                    self.ledger.complete()
                finally:
                    elapsed = monotonic() - started
                    self.observed[(request.role, number)] = _ObservedSend(
                        scope, trace, elapsed, actual_header["value"]
                    )
                    if self.inputs_path is not None:
                        append_json(
                            self.inputs_path,
                            {
                                "scope": scope.model_dump(mode="json"),
                                "request": generation_request_evidence(request),
                                "request_headers": {"x-session-id": actual_header["value"]},
                            },
                        )
            if actual_header["value"] != request.session_affinity:
                raise ValidationError("Integrated request affinity differs from the sent header.")
            return receipt


def _typed_eval_provider(trace: ProviderTrace) -> _EvalGenerationProvider:
    guard = trace.provider
    provider = getattr(guard, "wrapped", None)
    ledger = getattr(guard, "ledger", None)
    limiter = getattr(guard, "limiter", None)
    if not isinstance(provider, LocalProvider) or not isinstance(ledger, IntegratedLedger):
        raise ValidationError(
            "Integrated memory evaluation requires its guarded OpenRouter provider."
        )
    return _EvalGenerationProvider(provider, ledger, limiter)


async def record_generation(
    request: PreparedMemoryRequest,
    scope: AttemptScope,
    trace: ProviderTrace | None,
    output: Path,
) -> MemoryGeneration:
    started = monotonic()
    result: MemoryGeneration | None = None
    observed: _ObservedSend | None = None
    actual_header: dict[str, str | None] = {"value": None}
    try:
        if trace is None:
            raise ValidationError("Integrated memory evaluation has no generation trace.")
        typed_provider = _typed_eval_provider(trace)
        if typed_provider.ledger.current_scope != scope:
            raise ValidationError("Integrated memory evaluation attempt scope changed.")
        session_affinity = _client_session_id(typed_provider.provider)
        with _capture_actual_session_id(typed_provider.provider) as actual_header:
            _, config = await resolve_generation_context()
            result = await execute_memory_generation(
                request,
                provider=typed_provider,
                ledger=InMemoryGenerationLedger(),
                config=config,
                policy=get_generation_recovery_policy(),
                adapter=Adapter(config.provider),
                session_affinity=session_affinity,
            )
        if actual_header["value"] != session_affinity:
            raise ValidationError("Integrated request affinity differs from the sent header.")
        observed = typed_provider.observed.get((request.kind, typed_provider.counts[request.kind]))
        return result
    finally:
        append_json(
            output,
            {
                "scope": scope.model_dump(mode="json"),
                "raw": str(
                    observed.trace.response.get("text", "")
                    if observed
                    else trace.response.get("text", "")
                    if trace
                    else ""
                ),
                "valid": result is not None,
                "session_affinity": (
                    observed.trace.request.get("session_affinity") if observed else None
                ),
                "request_headers": {"x-session-id": actual_header["value"]},
                **provider_evidence(
                    observed.trace if observed else trace,
                    observed.elapsed if observed else monotonic() - started,
                ),
            },
        )


class MemoryDriver:
    def __init__(
        self,
        plan: IntegratedPlan,
        ledger: IntegratedLedger,
        campaign_id: UUID,
        directory: Path,
        resolve: GenerationResolver,
    ) -> None:
        self.plan = plan
        self.ledger = ledger
        self.campaign_id = campaign_id
        self.directory = directory
        self.resolve = resolve
        self.limiter = FreeRequestLimiter()
        self.session_scope = session_id_for_model(plan.session_scope, plan.generation_model or "")

    async def drain(self) -> None:
        for _ in range(self.plan.batch_count + self.plan.global_count + 1):
            self.ledger.ensure_healthy()
            async with dependencies.async_session() as db:
                jobs = await coordinate_memory(
                    db, self.campaign_id, session_scope=self.session_scope
                )
                await db.commit()
            if not jobs:
                return
            for job_id in jobs:
                await self._job(job_id)
        raise ValueError("integrated memory scheduling exceeded the planned transition bound")

    async def _job(self, job_id: UUID) -> None:
        async with dependencies.async_session() as db:
            job = await db.get(MemoryJob, job_id)
            if job is None or job.campaign_id != self.campaign_id:
                raise ValueError("integrated evaluation job identity changed")
            if job.attempt_count or job.state != "queued":
                raise ValueError("integrated evaluation stops before retrying a memory job")
            campaign = await db.get(Campaign, self.campaign_id)
            if campaign is None:
                raise ValueError("integrated evaluation campaign is missing")
            owner_id = campaign.user_id
            batch_id = job.batch_id
            source = await load_batch_input(db, self.campaign_id, batch_id)
            if tuple(turn.turn_id for turn in source.turns) != job.manifest.source_turn_ids:
                raise ValueError("persisted job sources differ from batch membership")
        _, expected_config = await self.resolve(owner_id)
        if (
            expected_config.provider != "openrouter"
            or expected_config.model != self.plan.generation_model
            or expected_config.max_tokens != self.plan.output_cap
        ):
            raise ValueError("integrated generation destination differs from the frozen plan")

        observed_provider: _EvalGenerationProvider | None = None

        def decorate(
            provider: AIProvider,
            config: ModelConfig,
            claim: JobClaim,
            requests: tuple[PreparedMemoryRequest, ...],
        ) -> GenerationProvider:
            nonlocal observed_provider
            if (
                not isinstance(provider, LocalProvider)
                or provider.provider_kind != "openrouter"
                or config.provider != "openrouter"
                or config.model != self.plan.generation_model
                or config.max_tokens != self.plan.output_cap
            ):
                raise ValueError("integrated generation destination differs from the frozen plan")
            source_hashes = {request.kind: request.source_hash for request in requests}

            def scope_for(request: GenerationRequest) -> AttemptScope:
                return AttemptScope(
                    run_id=self.plan.run_id,
                    campaign_id=self.campaign_id,
                    job_id=claim.job_id,
                    batch_id=claim.batch_id,
                    source_turn_ids=claim.manifest.source_turn_ids,
                    input_hash=source_hashes[
                        cast(Literal["batch", "summary", "facts", "global"], request.role)
                    ],
                    role=cast(Literal["summary", "facts", "global"], request.role),
                    provider=config.provider,
                    model=config.model,
                )

            observed_provider = _EvalGenerationProvider(
                provider,
                self.ledger,
                self.limiter,
                scope_for=scope_for,
                inputs_path=self.directory / "inputs.jsonl",
            )
            return observed_provider

        published = await job_execution.execute_job(
            self.campaign_id,
            job_id,
            provider_decorator=decorate,
            session_scope=self.session_scope,
        )
        if observed_provider is not None:
            await self._record_job_outputs(job_id, observed_provider)
        self.ledger.ensure_healthy()
        if not published:
            raise ValueError("memory job did not publish; review evidence before any retry")

    async def _record_job_outputs(self, job_id: UUID, provider: _EvalGenerationProvider) -> None:
        async with dependencies.async_session() as db:
            job = await db.get(MemoryJob, job_id)
            if job is None:
                raise ValueError("integrated evaluation job disappeared")
            rows = list(
                await db.scalars(
                    select(PersistedMemoryGeneration).where(
                        PersistedMemoryGeneration.job_id == job_id
                    )
                )
            )
        roles = ("summary", "facts") if job.kind == "batch" else ("global",)
        role_order = {role: index for index, role in enumerate(roles)}
        rows.sort(
            key=lambda row: (
                role_order.get(row.role, len(roles)),
                row.send_number or 0,
            )
        )
        for row in rows:
            if row.role not in roles or row.send_number is None:
                continue
            observed = provider.observed.get((row.role, row.send_number))
            if observed is None:
                continue
            receipt = (
                decode_receipt(row.receipt, row.raw_candidate) if row.receipt is not None else None
            )
            append_json(
                self.directory / "outputs.jsonl",
                {
                    "scope": observed.scope.model_dump(mode="json"),
                    "raw": receipt.text if receipt and receipt.text else "",
                    "valid": row.status == "valid",
                    "session_affinity": json.loads(row.request_identity_snapshot or "{}").get(
                        "session_affinity"
                    ),
                    "request_headers": {"x-session-id": observed.session_affinity},
                    **provider_evidence(
                        observed.trace if observed else None,
                        observed.elapsed if observed else 0.0,
                    ),
                },
            )
